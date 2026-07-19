# Cloud Cost Optimizer & Remediation Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** API-first FinOps tool that ingests AWS/Azure billing exports, detects orphaned resources, and generates decommission commands, with a glassmorphism dashboard.

**Architecture:** Hexagonal — pure-Python core (`app/core`: models, plugin registries, providers, rules, remediation, engine) with adapters for SQLite (`app/adapters`), FastAPI (`app/api`), and a static dashboard (`app/static`). Findings dedupe on `(resource_id, rule)`; ingest is idempotent via file content-hash.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, SQLAlchemy 2 (SQLite), pydantic v2, pytest, httpx TestClient, Playwright (Chromium), Chart.js (vendored), vanilla JS/CSS glassmorphism.

## Global Constraints

- No cloud SDK calls at runtime — remediation is **generated text only**, never executed.
- USD only; severity: high ≥ $50/mo, medium ≥ $10, low < $10; old snapshot threshold = 90 days.
- Rules must skip `state=unknown` resources (no false positives).
- Every endpoint gets API E2E tests before moving to the next task. Playwright journey must pass before MVP is declared done.
- `prompts.md` audit log updated every user turn (project rule).
- Commit after every green test cycle.

---

### Task 1: Scaffold, dependencies, core models + registries

**Files:**
- Create: `requirements.txt`, `.gitignore`, `app/__init__.py`, `app/core/__init__.py`, `app/core/models.py`, `app/core/registry.py`, `app/core/providers/__init__.py`, `app/core/rules/__init__.py`
- Test: `tests/unit/test_registry.py`

**Interfaces (Produces):**
- `NormalizedResource` dataclass: `provider:str, resource_id:str, resource_type:str  # disk|vm|ip|snapshot|other, region:str, billing_period:str  # YYYY-MM, monthly_cost:float, usage_hours:float, state:str, created_at:date|None, tags:dict, raw_ref:int|None`
- `FindingResult` dataclass: `resource:NormalizedResource, rule:str, category:str, severity:str, est_monthly_savings:float, reason:str`
- `provider(name)` decorator → registers `parse(file_bytes:bytes, billing_period:str|None) -> tuple[list[NormalizedResource], list[dict]]` (resources, row_errors)
- `rule(name, category)` decorator → registers `evaluate(resources:list[NormalizedResource]) -> list[FindingResult]`
- `get_provider(name)`, `all_rules() -> dict[str, RuleEntry]`, `severity_for(savings)` helper.

Steps: write failing registry tests (register/lookup/unknown-name KeyError, severity thresholds) → implement → pass → commit. Install deps into `.venv`.

### Task 2: Sample data generator

**Files:**
- Create: `sample_data/generate.py`, generated `sample_data/aws_cur.csv`, `sample_data/azure_costs.json`
- Test: `tests/unit/test_sample_data.py`

**Produces:** deterministic (seed=42) exports. AWS CUR columns: `identity/LineItemId, lineItem/UsageAccountId, lineItem/ResourceId, lineItem/ProductCode, lineItem/UsageType, lineItem/UsageAmount, lineItem/UnblendedCost, product/ProductName, product/region, lineItem/UsageStartDate, resourceTags/user:Name, resourceTags/aws:attachmentState, resourceTags/aws:createdDate, resourceTags/aws:cpuAvgPct`. Azure JSON: list of objects `ResourceId, ResourceType, MeterCategory, MeterName, CostInBillingCurrency, Quantity, ResourceLocation, Date, Tags (json str), AdditionalInfo (json str with attachmentState/createdDate/avgCpuPct/powerState)`.
Seeded waste: AWS — 3 unattached EBS vols, 2 stopped-but-billed EC2, 3 unassociated EIPs, 3 snapshots >90d; Azure — 3 unattached managed disks, 2 idle VMs, 2 unassociated public IPs, 3 old snapshots; plus ≥60 healthy noise rows total. Test asserts counts and determinism.

### Task 3: AWS parser

**Files:** Create `app/core/providers/aws.py`; Test `tests/unit/test_aws_parser.py`

**Produces:** `@provider("aws")` parse of CUR CSV → NormalizedResources. Type mapping from UsageType/ProductName: `EBS:Volume*`→disk, `BoxUsage`/EC2 instance→vm, `ElasticIP`→ip, `EBS:Snapshot*`→snapshot, else other. Aggregates rows by ResourceId (sum cost/usage). State from `resourceTags/aws:attachmentState` (else unknown); created_at from tag; cpu pct into tags. Row errors: missing ResourceId / unparsable cost → error list, parsing continues.

### Task 4: Azure parser

**Files:** Create `app/core/providers/azure.py`; Test `tests/unit/test_azure_parser.py`

**Produces:** `@provider("azure")` parse of JSON (list) **and** CSV with same fields. Type from ResourceType/MeterCategory: `Microsoft.Compute/disks`→disk, `virtualMachines`→vm, `publicIPAddresses`→ip, `snapshots`→snapshot. State/created/cpu from AdditionalInfo JSON; malformed AdditionalInfo → state unknown (not an error).

### Task 5: Rules + engine

**Files:** Create `app/core/rules/unattached_disks.py`, `idle_vms.py`, `orphaned_ips.py`, `old_snapshots.py`, `app/core/engine.py`; Tests `tests/unit/test_rules.py`, `tests/unit/test_engine.py`

**Produces:**
- unattached_disk: type=disk AND state in {available, unattached} → full cost.
- idle_vm: type=vm AND (state=stopped AND cost>0) OR (avg cpu pct tag < 3.0 AND usage_hours>0) → full cost; skip unknown.
- orphaned_ip: type=ip AND state=unassociated → full cost.
- old_snapshot: type=snapshot AND created_at < today-90d → full cost.
- `engine.run_rules(resources, today:date) -> list[FindingResult]` iterates registry (today injected for testability).
Tests: positive, negative, unknown-state skip per rule; engine returns combined + severity set.

### Task 6: Remediation generator + script renderer

**Files:** Create `app/core/remediation.py`; Test `tests/unit/test_remediation.py`

**Produces:**
- `build_plan(finding:FindingResult) -> RemediationPlan` where `RemediationPlan.steps: list[RemStep]`, `RemStep: order:int, intent:str, cli:str, sdk_code:str, destructive:bool`. Per rule/provider: verify step (describe/show, destructive=False) + decommission step (delete/release, destructive=True). AWS: `aws ec2 delete-volume|terminate-instances|release-address|delete-snapshot`; Azure: `az disk delete|vm delete|network public-ip delete|snapshot delete` with `--ids`/resource-group parsing from Azure ResourceId path. SDK snippets: boto3 / azure-mgmt oneliners.
- `render_script(findings_with_plans, provider) -> str` bash script, commented per finding (id, rule, savings), verify lines then destructive lines.
Tests: each rule×provider yields correct command containing the resource id; script contains shebang, all open findings, verify-before-delete ordering.

### Task 7: DB adapter (ORM + repositories)

**Files:** Create `app/adapters/__init__.py`, `app/adapters/orm.py`, `app/adapters/db.py`; Test `tests/unit/test_db.py`

**Produces:** SQLAlchemy models: `IngestedFile(id, provider, filename, sha256 unique, uploaded_at)`, `RawLine(id, file_id, line_no, payload_json)`, `Resource(id, provider, resource_id, resource_type, region, billing_period, monthly_cost, usage_hours, state, created_at, tags_json; unique (provider,resource_id,billing_period))`, `Scan(id, ran_at, resource_count, finding_count, total_savings)`, `Finding(id, provider, resource_id, rule, category, severity, est_monthly_savings, reason, status default "open", first_seen_scan_id, last_seen_scan_id; unique (resource_id, rule))`.
Repo functions (session-scoped): `upsert_resources`, `record_file(sha) -> (file, created:bool)`, `apply_findings(scan, results)` implementing dedupe/lifecycle: new→insert open; existing→update savings/last_seen (keep dismissed status); findings not in results & not dismissed→status stale. `init_db(path)`, `get_session`.
Tests: idempotent upsert, duplicate file detection, lifecycle (re-scan no dupes; dismissed survives; stale marking).

### Task 8: FastAPI endpoints + per-endpoint E2E tests

**Files:** Create `app/api/__init__.py`, `app/api/schemas.py`, `app/api/main.py`; Test `tests/api/test_endpoints.py`

**Produces:** endpoints per spec §6 (`/api/ingest`, `/api/analyze`, `/api/findings`, `PATCH /api/findings/{id}`, `/api/findings/{id}/remediation`, `/api/remediation/script`, `/api/summary`, `/api/scans`, `/health`, `/` static). App factory `create_app(db_path)` for test isolation (tmp DB per test). Error envelope `{"error": {"message", "details"}}`.
Tests (TestClient, run after each endpoint is built): health; ingest ok + rows_failed + duplicate no-op + 422 garbage + unknown provider 422; analyze counts + re-analyze no dupes; findings filters; PATCH lifecycle + 404; remediation plan content; script download (text/x-shellscript, contains commands); summary aggregates; scans history. Full-flow test: ingest both samples → analyze → summary totals > 0.

### Task 9: Glassmorphism dashboard

**Files:** Create `app/static/index.html`, `app/static/style.css`, `app/static/app.js`, `app/static/chart.umd.js` (vendored from installed npm cache or CDN download at build time — must end up local, CSP-free).

**Produces:** spec §7 UI. Dark glass default + light glass via `data-theme` attr toggle persisted in localStorage. Cards: `background: rgba(...); backdrop-filter: blur(18px); border:1px solid rgba(255,255,255,.18); border-radius:16px`. Components with element ids used by Playwright: `#tile-waste, #tile-open, #tile-resources, #tile-annual, #chart-category, #chart-provider, #chart-trend, #top-offenders, #findings-table, #upload-form, #provider-select, #file-input, #btn-analyze, #btn-theme, #btn-script-aws, #btn-script-azure, #toast`. Row expand shows verify+remediate CLI blocks with copy buttons (`.btn-copy`), dismiss + mark-remediated buttons calling PATCH. Empty states when no data.

### Task 10: Playwright E2E suite (Chromium)

**Files:** Create `tests/e2e/conftest.py` (session fixture: launch uvicorn subprocess on port 8765 with temp DB, wait for /health), `tests/e2e/test_journey.py`
- Install: `pip install pytest-playwright` + `playwright install chromium`

**Tests:** smoke (dashboard loads, empty state visible); full journey (upload `sample_data/aws_cur.csv` via UI → analyze → tiles nonzero → charts canvases present → expand first finding → CLI text contains resource id → copy button → dismiss updates status badge → script download responds 200); theme toggle flips `data-theme` and persists after reload; azure upload journey.

### Task 11: README + final verification

**Files:** Create `README.md` (run instructions, API table, architecture summary, screenshots note); update `prompts.md`.
Run in order: full pytest unit+api suite → Playwright suite headless Chromium → manual uvicorn boot check. All green → final commit. Use superpowers:verification-before-completion.

---

## Self-review

Spec coverage: ingest(T3,T4,T8), rules(T5), remediation+script(T6,T8), lifecycle+scans(T7,T8), dashboard+toggle(T9), sample data(T2), tests(T1–T10), README(T11). Types consistent: NormalizedResource/FindingResult/RemediationPlan defined T1/T6 and consumed by name elsewhere. No placeholders — code-level detail is intentionally carried in Produces/Interfaces blocks; executor is the plan author in-session.
