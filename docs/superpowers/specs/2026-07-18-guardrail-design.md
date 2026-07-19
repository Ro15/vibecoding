# Project 2 — Enterprise Security Guardrail Auditor — Design Spec

Date: 2026-07-18
Status: Approved (monorepo + scope decisions locked Turn 12)

## Purpose

Scan infrastructure-as-code (Terraform HCL, CloudFormation, `terraform show -json`
plan output) against a security baseline, flag high-risk patterns (public S3, open
SSH/RDP, unencrypted storage, public DBs, wildcard IAM), and present a **Risk Score**
dashboard. Read-only auditor — it never mutates infrastructure.

## Architecture (on the shared `common` core)

```
apps/guardrail/
  core/
    models.py        IacResource, Finding (dataclasses)
    registry.py      parser + policy registries (built on common.registry)
    parsers/
      hcl.py         @parser("hcl")            Terraform .tf via python-hcl2
      cloudformation.py @parser("cloudformation")  YAML/JSON
      tfplan.py      @parser("tfplan")         terraform show -json
    policies/
      s3.py sg.py rds.py ebs.py iam.py         @policy(name, severity, framework, rtypes)
    scoring.py       risk score (0–100, higher=worse) + letter grade
    engine.py        run_policies(resources) -> findings  (type-indexed dispatch)
  adapters/ orm.py db.py        SQLite: scans, findings
  api/ schemas.py main.py       FastAPI (make_app from common)
  static/ index.html style.css app.js   glassmorphism risk dashboard
  sample_data/ generate.py + insecure.tf, insecure_cfn.yaml, tfplan.json, secure.tf
```

## Normalized IR

`IacResource`: `address, provider, rtype, raw_type, name, config: dict, source, source_format`.
Canonical `config` per rtype (each parser maps its native shape to this):
- **s3_bucket**: `acl`, `encrypted`, `public_access_block`, `versioning`
- **security_group**: `ingress: [{from_port, to_port, cidr, protocol}]`
- **ec2_instance**: `associate_public_ip`
- **rds_instance**: `publicly_accessible`, `encrypted`
- **ebs_volume**: `encrypted`
- **iam_policy**: `statements: [{effect, actions, resources}]`

Provider from raw type prefix (`aws_*`/`AWS::*` → aws). Unknown rtype → `other` (rules skip).

## Policies (CIS-aligned starter baseline)

| Policy | Signal | Severity | Framework |
|---|---|---|---|
| s3_public_acl | acl in {public-read, public-read-write} | high | CIS 2.1.5 |
| s3_no_encryption | encrypted is False | medium | CIS 2.1.1 |
| s3_no_versioning | versioning is False | low | CIS 2.1.3 |
| sg_open_ssh | ingress 0.0.0.0/0 covering port 22 | high | CIS 5.2 |
| sg_open_rdp | ingress 0.0.0.0/0 covering port 3389 | high | CIS 5.2 |
| sg_open_all_ports | ingress 0.0.0.0/0, ports 0–65535 | critical | CIS 5.3 |
| rds_public | publicly_accessible is True | high | CIS 2.3.3 |
| rds_unencrypted | encrypted is False | medium | CIS 2.3.1 |
| ebs_unencrypted | encrypted is False | medium | CIS 2.2.1 |
| iam_wildcard | statement Allow with action `*` on resource `*` | high | CIS 1.16 |

Each finding carries the source (file + resource address) and a remediation string.

## Risk Score

Severity weights: critical 40, high 20, medium 8, low 3. `raw = Σ weights`;
`score = min(100, raw)` (0 = clean, 100 = max risk). Grade: 0→A+, <15→A, <30→B,
<50→C, <75→D, else F. Dashboard shows a gauge + grade.

## Complexity

Parse O(F) in file bytes. Resources indexed by rtype; each policy declares its rtypes,
so dispatch is O(R + M) (R resources, M applicable pairs) — linear, never rules×resources.
Score O(findings). Space O(R + findings).

## API

`POST /api/ingest` (file + format), `POST /api/scan`, `GET /api/findings`
(filters: severity, framework, rtype), `GET /api/summary` (score, grade, by-severity,
by-rtype, by-framework), `GET /api/findings/{id}` (detail + remediation),
`GET /api/scans`, `GET /health`, `GET /`.

## Testing

Unit: each parser (incl. secure=no-findings), each policy (positive/negative), scoring,
engine. API E2E: every endpoint after it's built. Playwright: upload → scan → gauge +
findings render → filter → expand remediation → theme toggle. agent-browser manual pass.
