# Cloud Cost Optimizer & Remediation Engine — Design Spec

Date: 2026-07-18
Status: Approved architecture (v2), pending spec review
Owner: Ro (product) / Claude (architect + implementation, no manual edits)

## 1. Purpose

A Python, API-first FinOps tool that ingests AWS and Azure billing exports (CSV/JSON), detects orphaned/wasteful resources, estimates monthly savings, and generates the exact CLI commands and SDK code needed to decommission the waste. Free database (SQLite), glassmorphism web dashboard. The tool **generates** remediation logic; it never executes it against cloud accounts.

## 2. Scope

### In scope (MVP)
- Ingest AWS CUR-style CSV and Azure cost-export JSON/CSV via API upload.
- Four detection rules: unattached disks, idle/stopped VMs, unassociated elastic/public IPs, old snapshots (>90 days).
- Per-finding remediation: verify command, decommission CLI command (aws/az), equivalent SDK snippet (boto3 / azure-sdk).
- Per-provider downloadable remediation shell script for open findings.
- Findings lifecycle: open → dismissed / remediated (manual state change via API + UI).
- Scan history (each analysis run recorded; dashboard trend).
- Glassmorphism dashboard with dark/light theme toggle: summary tiles, waste by category, waste by provider, top offenders, findings table with copyable commands, upload + analyze controls.
- Generated realistic sample exports (seeded waste) for demo and tests.
- Testing: pytest unit tests (parsers, each rule, remediation generator), API end-to-end tests per endpoint, Playwright full-user-journey tests on Chrome.

### Out of scope (backlog)
- Executing remediation against real accounts; auth (API key/SSO); GCP; Postgres; scheduled ingestion from S3/Azure APIs; multi-currency (USD assumed); RI/savings-plan recommendations.

## 3. Architecture (v2 — hexagonal, plugin-based)

Single FastAPI process. Pure-Python core domain with framework-free logic; FastAPI, SQLite, and the dashboard are thin adapters.

```
app/
  core/                    # pure domain — no FastAPI/SQLAlchemy imports
    models.py              # dataclasses: NormalizedResource, Finding, RemediationPlan, Scan
    registry.py            # provider + rule plugin registries (decorator-based)
    providers/
      aws.py               # @provider("aws")  CUR CSV → NormalizedResource[]
      azure.py             # @provider("azure") cost export JSON/CSV → NormalizedResource[]
    rules/
      unattached_disks.py  # @rule("unattached_disk", category="storage")
      idle_vms.py          # @rule("idle_vm", category="compute")
      orphaned_ips.py      # @rule("orphaned_ip", category="network")
      old_snapshots.py     # @rule("old_snapshot", category="storage")
    remediation.py         # Finding → RemediationPlan (structured steps, destructive flags)
    engine.py              # run_scan(resources) → findings (dedupe + lifecycle merge)
  adapters/
    db.py                  # SQLite via SQLAlchemy; repositories
    orm.py                 # ORM models: raw_lines, resources, scans, findings
  api/
    main.py                # FastAPI app, routes, static mount
    schemas.py             # pydantic request/response models
  static/
    index.html, app.js, style.css   # glassmorphism dashboard, Chart.js (vendored), theme toggle
sample_data/
  generate.py              # deterministic generator; aws_cur.csv, azure_costs.json
tests/
  unit/                    # parsers, rules, remediation, engine
  api/                     # per-endpoint E2E via httpx/TestClient
  e2e/                     # Playwright (Chrome) full journey
prompts.md                 # audit log (project rule)
```

### Key mechanisms
- **Plugin registries**: `@provider(name)` and `@rule(name, category)` decorators register parse/evaluate callables; engine iterates the registry. New provider/rule = new file, no engine edits.
- **Idempotent ingest**: uploaded file content-hash stored; duplicate upload → no-op response. Resources upsert on `(provider, resource_id, billing_period)`. Raw line items staged in `raw_lines` for re-normalization.
- **Finding identity**: dedupe key `(resource_id, rule)`. Re-scan updates existing findings (cost/savings refresh), never duplicates. Dismissed findings stay dismissed across re-scans. Findings for resources no longer present are marked `stale`.
- **RemediationPlan as data**: `steps: [{order, intent, cli, sdk_code, destructive}]`; rendered to text/script at the API edge. Verify steps `destructive=false`, delete steps `destructive=true`.
- **Scan records**: every `/analyze` creates a Scan row (timestamp, resource count, findings count, total est. savings) → dashboard trend.

## 4. Normalized resource model

`NormalizedResource`: `provider, resource_id, resource_type (disk|vm|ip|snapshot|other), region, billing_period, monthly_cost, usage_hours, state (attached|available|stopped|running|associated|unassociated|unknown), created_at, tags (dict), raw_ref`.

Parsers map provider schemas to this shape:
- AWS CUR columns: `lineItem/ResourceId`, `lineItem/UsageType`, `lineItem/UnblendedCost`, `lineItem/UsageAmount`, `product/ProductName`, `resourceTags/*`.
- Azure export fields: `ResourceId`, `MeterCategory`, `CostInBillingCurrency`, `Quantity`, `Tags`, `AdditionalInfo`.
- Attachment/state and creation date come from tags/AdditionalInfo in the sample data; real exports vary — parsers degrade to `state=unknown` (rules skip unknowns rather than false-positive).

## 5. Detection rules (billing-data heuristics)

| Rule | Signal | Est. savings |
|---|---|---|
| unattached_disk | resource_type=disk AND state=available/unattached | full monthly cost |
| idle_vm | resource_type=vm AND (state=stopped with nonzero cost OR usage_hours ≥ 95% of period with cpu-equivalent usage metric ≈ 0 from tags/AdditionalInfo) | full monthly cost |
| orphaned_ip | resource_type=ip AND state=unassociated (AWS bills unassociated EIPs — the charge is the signal) | full monthly cost |
| old_snapshot | resource_type=snapshot AND created_at > 90 days ago | full monthly cost |

Severity: high ≥ $50/mo, medium ≥ $10, low < $10.

## 6. API surface

| Method & path | Purpose |
|---|---|
| `POST /api/ingest` | multipart upload + `provider` field; returns rows_ok / rows_failed (row-level errors), resources upserted, duplicate-file flag. 422 on malformed file. |
| `POST /api/analyze` | run all rules; returns scan summary (findings new/updated/stale, total est. savings) |
| `GET /api/findings` | filters: provider, rule, status, min_savings; sorted by savings desc |
| `PATCH /api/findings/{id}` | update status (open/dismissed/remediated) |
| `GET /api/findings/{id}/remediation` | structured RemediationPlan + rendered CLI text + SDK snippet |
| `GET /api/remediation/script?provider=aws\|azure` | downloadable shell script (verify + delete, commented per finding) for open findings |
| `GET /api/summary` | tiles + chart aggregates: totals, by category, by provider, top offenders, scan trend |
| `GET /api/scans` | scan history |
| `GET /health` | liveness |
| `GET /` | dashboard |

No auth (localhost MVP); noted as production-hardening item.

## 7. Dashboard (glassmorphism)

Single page, vanilla JS + vendored Chart.js (no build toolchain). Frosted translucent cards (`backdrop-filter: blur`), gradient background, **dark/light theme toggle** (persisted in localStorage; both fully styled). Components: 4 summary tiles (total monthly waste, open findings, resources analyzed, potential annual savings); charts: waste by category (doughnut), waste by provider (bar), scan trend (line); top-offenders list; findings table (filterable, status badges, per-row expand showing verify + remediation commands with copy buttons, dismiss/mark-remediated actions); upload control (provider select + file) and "Run Analysis" button; download-script buttons per provider. Empty states for pre-ingest views.

## 8. Sample data

`sample_data/generate.py` — deterministic (fixed seed): ~120 AWS CUR rows and ~80 Azure rows across 2 regions each; seeded waste: 6 unattached disks, 4 idle/stopped VMs, 5 unassociated IPs, 6 old snapshots, plus healthy resources as noise. Committed generated files so the demo works without running the generator.

## 9. Error handling

- Ingest: per-row validation; bad rows collected with reason, good rows proceed; whole-file rejection only when structurally unreadable (422).
- Unknown columns ignored; missing optional fields → degraded state=unknown (rules skip).
- API errors: consistent JSON error envelope; FastAPI validation → 422.
- Dashboard: toast on API errors; empty-state panels instead of broken charts.

## 10. Testing strategy

- **Unit (pytest)**: parser fixtures → expected NormalizedResources; each rule against seeded resource sets (positive + negative + unknown-state cases); remediation generator per finding type; engine dedupe/lifecycle (re-scan no duplicates, dismissal survives).
- **API E2E (pytest + TestClient)**: every endpoint exercised after it is built — full flow ingest→analyze→findings→remediation→script; duplicate upload idempotency; malformed upload 422; PATCH lifecycle.
- **Browser E2E (Playwright, Chromium/Chrome)**: full user journey — load dashboard → upload sample export → run analysis → tiles/charts populated → expand a finding → remediation command visible and copyable → dismiss a finding → download script; plus smoke test and theme-toggle test. Runs against a live uvicorn instance with a temp DB.
- Definition of done per endpoint: unit + API tests green before moving on; Playwright suite green before MVP is declared done.

## 11. Milestones (target 4–6 h total)

1. Scaffold + core models + registries + sample data generator (~45 min)
2. Parsers + unit tests (~45 min)
3. Rules engine + rules + unit tests (~60 min)
4. Remediation generator + script export + tests (~45 min)
5. API adapters + per-endpoint E2E tests (~60 min)
6. Dashboard (glassmorphism, toggle) (~75 min)
7. Playwright suite + full verification pass (~45 min)

## 12. Production-hardening backlog

HTTPS, Postgres swap (repo adapter ready), CloudWatch/Azure Monitor metrics for true idleness, multi-currency, SSO/RBAC beyond API keys, real cloud execution (executor is simulated in v1.1).

## 13. v1.1 feature expansion (approved 2026-07-18, Turn 10)

1. **Realized savings**: marking a finding `remediated` (via PATCH or execution) stamps `remediated_at` + freezes `realized_monthly_savings`; summary exposes the realized total; new dashboard tile.
2. **Multi-month trends**: `GET /api/trends` groups resources by `billing_period` and runs rules per period (findings table stays "current-state"; analyze scans only the latest period). Prev-month sample files added. Dashboard "Waste by month" chart.
3. **Policy engine**: `policies` table (key/value overrides over defaults): snapshot retention, idle-CPU %, rightsize-CPU %, stopped-VM age, severity bands, owner tag keys, untagged min cost, LB/NAT thresholds. `GET/PUT /api/policies` + settings panel.
4. **Ownership**: `owner` tag parsed by all providers; findings carry owner; summary `by_owner`; new `untagged_resource` rule (category `governance`, remediation = tagging command, min-cost threshold).
5. **Scheduled scans**: APScheduler; `GET/PUT /api/schedule` (enabled/interval/webhook_url stored as policies); job = run scan + POST JSON digest to webhook.
6. **GCP provider**: `@provider("gcp")` parsing billing-export JSON (nested service/sku/labels schema) with disk/vm/ip/snapshot/lb/natgw mapping; gcloud remediation commands.
7. **New rules**: `oversized_vm` (running, CPU between idle and rightsize thresholds → savings = 50% of cost, resize plan), `idle_load_balancer` (requests below threshold), `unused_nat_gateway` (GB processed below threshold), `aged_stopped_vm` (stoppedDate older than threshold → terminate plan; idle_vm defers to it).
8. **Guarded execution (simulated)**: `POST /api/findings/{id}/execute` `{dry_run, approve}` — non-dry-run requires `approve:true`; SimulatedExecutor echoes commands (no cloud credentials in scope — by design the tool still never touches a real account); `executions` audit table + `GET /api/executions`; real-run marks finding remediated.
9. **Auth**: optional `X-API-Key` — viewer key (reads) / operator key (mutations + execution) via `COSTOPT_VIEWER_KEY` / `COSTOPT_OPERATOR_KEY` env; unset = auth off (local mode). 401 (missing) / 403 (wrong).
10. **FOCUS ingestion**: `@provider("focus")` parsing FinOps-Foundation FOCUS-style CSV/JSON; `ProviderName` column sets each resource's actual provider.
