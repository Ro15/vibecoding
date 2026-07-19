# CostOpt — Cloud Cost Optimizer & Remediation Engine

API-first FinOps tool: ingest AWS / Azure / GCP / FOCUS billing exports (CSV/JSON),
detect waste with nine policy-driven rules (unattached disks, idle VMs, orphaned IPs,
old snapshots, oversized VMs, idle load balancers, unused NAT gateways, aged stopped
VMs, untagged resources), and **generate** the exact CLI commands / SDK code to
decommission it. SQLite storage, glassmorphism dashboard (dark/light), fully tested.

Extras beyond the MVP: realized-savings tracking, multi-month trends, a policy engine
with a settings UI, tag-based ownership, scheduled scans with webhook digests, guarded
**simulated** execution with an audit trail, and optional API-key auth
(`COSTOPT_VIEWER_KEY` / `COSTOPT_OPERATOR_KEY` env vars; unset = local mode).

> Safety: the tool never executes anything against a cloud account. Every finding yields
> a *verify* command first, then the destructive command, plus a Python SDK equivalent.
> The execution endpoint uses a simulated executor that echoes commands and records an
> audit entry — swapping in a real executor is a deliberate, separate step.

## Run

```bash
python -m uvicorn apps.costopt.api.main:app --port 8000    # from the repo root
```

Open http://127.0.0.1:8000 — upload `apps/costopt/sample_data/aws_cur.csv` (provider AWS)
and `apps/costopt/sample_data/azure_costs.json` (provider Azure), press **Run Analysis**.
Interactive API docs at `/docs`.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/ingest` | multipart upload (`file`, `provider=aws\|azure\|gcp\|focus`); idempotent by content hash |
| POST | `/api/analyze` | run all detection rules; findings dedupe on (resource, rule); records a scan |
| GET | `/api/findings` | filters: `provider`, `rule`, `status`, `min_savings` |
| PATCH | `/api/findings/{id}` | status: `open` / `dismissed` / `remediated` |
| GET | `/api/findings/{id}/remediation` | verify + decommission CLI, SDK snippet, destructive flags |
| GET | `/api/remediation/script?provider=` | downloadable bash script for all open findings |
| POST | `/api/findings/{id}/execute` | guarded simulated execution (`dry_run`, `approve`) — audited |
| GET | `/api/executions` | execution audit trail |
| GET/PUT | `/api/policies` | detection thresholds (retention, CPU %, severity bands, tag keys…) |
| GET/PUT | `/api/schedule` | scheduled scans (APScheduler) + webhook digest URL |
| GET | `/api/trends` | per-billing-period waste (multi-month trend) |
| GET | `/api/summary` | dashboard aggregates + by-owner + realized savings + scan trend |
| GET | `/api/scans` | scan history |

## Sample data

`sample_data/generate.py` deterministically produces AWS/Azure/GCP/FOCUS exports for two
billing months with 40+ seeded waste findings (≈ $1,100/mo) among healthy noise.

Design spec: `docs/superpowers/specs/2026-07-18-cloud-cost-optimizer-design.md` ·
Plan: `docs/superpowers/plans/2026-07-18-cloud-cost-optimizer.md`
