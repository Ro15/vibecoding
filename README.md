# CostOpt — Cloud Cost Optimizer & Remediation Engine

API-first FinOps tool: ingest AWS/Azure billing exports (CSV/JSON), detect orphaned
resources (unattached disks, idle VMs, orphaned IPs, old snapshots), estimate monthly
savings, and **generate** the exact CLI commands / SDK code to decommission the waste.
SQLite storage, glassmorphism dashboard (dark/light), fully tested (pytest + Playwright).

> Safety: the tool never executes anything against a cloud account. Every finding yields
> a *verify* command first, then the destructive command, plus a Python SDK equivalent.

## Quick start

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Windows
.venv/Scripts/python -m uvicorn app.api.main:app --port 8000
```

Open http://127.0.0.1:8000 — upload `sample_data/aws_cur.csv` (provider AWS) and
`sample_data/azure_costs.json` (provider Azure), press **Run Analysis**.
Interactive API docs: http://127.0.0.1:8000/docs

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/ingest` | multipart upload (`file`, `provider=aws\|azure`); idempotent by content hash; row-level errors |
| POST | `/api/analyze` | run all detection rules; findings dedupe on (resource, rule); records a scan |
| GET | `/api/findings` | filters: `provider`, `rule`, `status`, `min_savings` |
| PATCH | `/api/findings/{id}` | status: `open` / `dismissed` / `remediated` |
| GET | `/api/findings/{id}/remediation` | structured plan: verify + decommission CLI, SDK snippet, destructive flags |
| GET | `/api/remediation/script?provider=` | downloadable bash script for all open findings |
| GET | `/api/summary` | dashboard aggregates + scan trend |
| GET | `/api/scans` | scan history |
| GET | `/health` | liveness |

## Architecture

Hexagonal: pure-Python core (`app/core` — parsers, rules, remediation as plugin
registries) with thin adapters (`app/adapters` SQLite, `app/api` FastAPI,
`app/static` dashboard). New provider or rule = one new file with a decorator.
Detection heuristics operate on billing data alone: attachment state, power state,
usage, and age signals carried in export tags/AdditionalInfo; resources whose state
is unknown are skipped rather than false-positived.

Design spec: `docs/superpowers/specs/2026-07-18-cloud-cost-optimizer-design.md`
Implementation plan: `docs/superpowers/plans/2026-07-18-cloud-cost-optimizer.md`
Prompt audit log: `prompts.md`

## Tests

```bash
.venv/Scripts/python -m pytest tests/unit tests/api -q     # 72 unit + API E2E tests
.venv/Scripts/python -m playwright install chromium        # once
.venv/Scripts/python -m pytest tests/e2e -q                # 10 browser journey tests
```

## Sample data

`sample_data/generate.py` deterministically produces both exports with 21 seeded
waste findings (≈ $592.50/mo) among healthy noise resources.

## Production-hardening backlog

Auth (API key/SSO), Postgres swap, real CUR/FOCUS schema coverage, CloudWatch/Azure
Monitor metrics for true idleness, gated execution engine with audit trail, GCP.
