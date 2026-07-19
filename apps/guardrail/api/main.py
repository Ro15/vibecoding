"""Guardrail FastAPI adapter, built on common.api."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import File, Form, HTTPException, UploadFile

from apps.guardrail.adapters import db as repo
from apps.guardrail.core.engine import run_policies
from apps.guardrail.core.registry import all_parsers, get_parser
from apps.guardrail.api.schemas import FindingOut, IngestResponse, ScanOut
from common.api import make_app, mount_dashboard

STATIC_DIR = Path(__file__).parents[1] / "static"

# format -> default filename hint
FORMAT_HINTS = {"hcl": "main.tf", "cloudformation": "template.yaml", "tfplan": "plan.json"}


def create_app(db_path: str = "guardrail.db"):
    app = make_app("Enterprise Security Guardrail Auditor",
                   "Audit Terraform / CloudFormation against a security baseline.",
                   "1.0.0")
    engine = repo.init_db(db_path)

    @app.post("/api/ingest", response_model=IngestResponse)
    async def ingest(file: UploadFile = File(...), format: str = Form(...)):
        if format not in all_parsers():
            raise HTTPException(422, detail=f"unknown format {format!r}; "
                                            f"expected one of {sorted(all_parsers())}")
        content = await file.read()
        filename = file.filename or FORMAT_HINTS.get(format, "upload")
        try:
            resources, errors = get_parser(format)(content, filename)
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        findings = run_policies(resources)
        with repo.session_scope(engine) as s:
            scan = repo.record_scan(s, filename, format, len(resources), findings)
            return IngestResponse(source=filename, source_format=format,
                                  resource_count=len(resources), parse_errors=errors[:50],
                                  scan_id=scan.id, finding_count=scan.finding_count,
                                  risk_score=scan.risk_score, grade=scan.grade)

    @app.get("/api/findings", response_model=list[FindingOut])
    def findings(scan_id: int | None = None, severity: str | None = None,
                 framework: str | None = None, rtype: str | None = None):
        with repo.session_scope(engine) as s:
            rows = repo.list_findings(s, scan_id=scan_id, severity=severity,
                                      framework=framework, rtype=rtype)
            return [FindingOut.model_validate(r, from_attributes=True) for r in rows]

    @app.get("/api/findings/{finding_id}", response_model=FindingOut)
    def finding(finding_id: int):
        with repo.session_scope(engine) as s:
            try:
                row = repo.get_finding(s, finding_id)
            except KeyError as exc:
                raise HTTPException(404, detail=str(exc)) from exc
            return FindingOut.model_validate(row, from_attributes=True)

    @app.get("/api/summary")
    def summary():
        with repo.session_scope(engine) as s:
            latest = repo.latest_scan(s)
            if latest is None:
                return {"risk_score": 0, "grade": "A+", "finding_count": 0,
                        "resource_count": 0, "source": None, "by_severity": {},
                        "by_rtype": {}, "by_framework": {}, "scan_trend": []}
            rows = repo.list_findings(s, scan_id=latest.id)
            by_sev: dict[str, int] = {}
            by_rtype: dict[str, int] = {}
            by_fw: dict[str, int] = {}
            for f in rows:
                by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
                by_rtype[f.rtype] = by_rtype.get(f.rtype, 0) + 1
                by_fw[f.framework] = by_fw.get(f.framework, 0) + 1
            return {
                "risk_score": latest.risk_score, "grade": latest.grade,
                "finding_count": latest.finding_count,
                "resource_count": latest.resource_count,
                "source": latest.source, "source_format": latest.source_format,
                "by_severity": by_sev, "by_rtype": by_rtype, "by_framework": by_fw,
                "scan_trend": [{"scan_id": sc.id, "risk_score": sc.risk_score,
                                "grade": sc.grade, "source": sc.source,
                                "finding_count": sc.finding_count}
                               for sc in repo.list_scans(s)],
            }

    @app.get("/api/scans", response_model=list[ScanOut])
    def scans():
        with repo.session_scope(engine) as s:
            return [ScanOut(id=sc.id, ran_at=sc.ran_at.isoformat(), source=sc.source,
                            source_format=sc.source_format,
                            resource_count=sc.resource_count,
                            finding_count=sc.finding_count, risk_score=sc.risk_score,
                            grade=sc.grade)
                    for sc in repo.list_scans(s)]

    mount_dashboard(app, STATIC_DIR)
    return app


app = create_app(os.environ.get("GUARDRAIL_DB", "guardrail.db"))
