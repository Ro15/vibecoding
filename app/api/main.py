"""FastAPI adapter — thin shell over the core domain."""
from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.adapters import db as repo
from app.core import engine as rules_engine
import app.core.providers  # noqa: F401  (registers aws/azure parsers)
from app.core.registry import all_providers, get_provider
from app.core.models import FindingResult
from app.core.remediation import build_plan, render_script
from app.api.schemas import (AnalyzeResponse, FindingOut, IngestResponse,
                             RemediationOut, ScanOut, StatusPatch)

STATIC_DIR = Path(__file__).parents[1] / "static"


def _finding_to_result(row) -> FindingResult:
    """Rehydrate a stored finding into a core FindingResult for remediation."""
    from app.core.models import NormalizedResource
    return FindingResult(
        resource=NormalizedResource(
            provider=row.provider, resource_id=row.resource_id,
            resource_type=row.resource_type, region=row.region,
            billing_period="", monthly_cost=row.est_monthly_savings,
            usage_hours=0.0, state="", created_at=None, tags={}),
        rule=row.rule, category=row.category, severity=row.severity,
        est_monthly_savings=row.est_monthly_savings, reason=row.reason)


def create_app(db_path: str = "costopt.db") -> FastAPI:
    app = FastAPI(title="Cloud Cost Optimizer & Remediation Engine",
                  description="FinOps API: ingest billing exports, detect orphaned "
                              "resources, generate decommission commands.",
                  version="1.0.0")
    engine = repo.init_db(db_path)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        return JSONResponse(status_code=500,
                            content={"error": {"message": str(exc), "details": None}})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/ingest", response_model=IngestResponse)
    async def ingest(file: UploadFile = File(...), provider: str = Form(...)):
        if provider not in all_providers():
            raise HTTPException(422, detail=f"unknown provider {provider!r}; "
                                            f"expected one of {sorted(all_providers())}")
        content = await file.read()
        sha = hashlib.sha256(content).hexdigest()
        with repo.session_scope(engine) as s:
            record, created = repo.record_file(s, provider, file.filename or "upload", sha)
            if not created:
                return IngestResponse(provider=provider, filename=file.filename or "upload",
                                      duplicate=True, rows_ok=0, rows_failed=0,
                                      row_errors=[], resources_upserted=0)
            try:
                resources, errors = get_provider(provider)(content)
            except ValueError as exc:
                s.rollback()
                raise HTTPException(422, detail=str(exc)) from exc
            repo.stage_raw_lines(s, record.id, [{"reason": e["reason"], "line": e["line"]}
                                                for e in errors])
            upserted = repo.upsert_resources(s, resources)
            return IngestResponse(provider=provider, filename=file.filename or "upload",
                                  duplicate=False, rows_ok=len(resources),
                                  rows_failed=len(errors), row_errors=errors[:50],
                                  resources_upserted=upserted)

    @app.post("/api/analyze", response_model=AnalyzeResponse)
    def analyze():
        with repo.session_scope(engine) as s:
            rows = repo.list_resources(s)
            resources = [repo.to_normalized(r) for r in rows]
            results = rules_engine.run_rules(resources)
            scan = repo.create_scan(s, resource_count=len(resources))
            stats = repo.apply_findings(s, scan, results)
            return AnalyzeResponse(scan_id=scan.id, resource_count=len(resources),
                                   findings_new=stats["new"], findings_updated=stats["updated"],
                                   findings_stale=stats["stale"],
                                   open_findings=scan.finding_count,
                                   total_est_monthly_savings=scan.total_savings)

    @app.get("/api/findings", response_model=list[FindingOut])
    def findings(provider: str | None = None, rule: str | None = None,
                 status: str | None = None, min_savings: float | None = None):
        with repo.session_scope(engine) as s:
            rows = repo.list_findings(s, provider=provider, rule=rule,
                                      status=status, min_savings=min_savings)
            return [FindingOut.model_validate(r, from_attributes=True) for r in rows]

    @app.patch("/api/findings/{finding_id}", response_model=FindingOut)
    def patch_finding(finding_id: int, body: StatusPatch):
        with repo.session_scope(engine) as s:
            try:
                row = repo.set_finding_status(s, finding_id, body.status)
            except KeyError as exc:
                raise HTTPException(404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(422, detail=str(exc)) from exc
            return FindingOut.model_validate(row, from_attributes=True)

    @app.get("/api/findings/{finding_id}/remediation", response_model=RemediationOut)
    def remediation(finding_id: int):
        with repo.session_scope(engine) as s:
            try:
                row = repo.get_finding(s, finding_id)
            except KeyError as exc:
                raise HTTPException(404, detail=str(exc)) from exc
            plan = build_plan(_finding_to_result(row))
            return RemediationOut(finding_id=row.id, rule=plan.rule, provider=plan.provider,
                                  resource_id=plan.resource_id,
                                  steps=[vars(step) for step in plan.steps])

    @app.get("/api/remediation/script")
    def remediation_script(provider: str):
        if provider not in all_providers():
            raise HTTPException(422, detail=f"unknown provider {provider!r}")
        with repo.session_scope(engine) as s:
            rows = repo.list_findings(s, provider=provider, status="open")
            script = render_script([(r.id, _finding_to_result(r)) for r in rows], provider)
            return PlainTextResponse(script, media_type="text/x-shellscript",
                                     headers={"Content-Disposition":
                                              f"attachment; filename=remediate_{provider}.sh"})

    @app.get("/api/summary")
    def summary():
        with repo.session_scope(engine) as s:
            open_rows = repo.list_findings(s, status="open")
            resources = repo.list_resources(s)
            by_category: dict[str, float] = {}
            by_provider: dict[str, float] = {}
            for f in open_rows:
                by_category[f.category] = round(by_category.get(f.category, 0) + f.est_monthly_savings, 2)
                by_provider[f.provider] = round(by_provider.get(f.provider, 0) + f.est_monthly_savings, 2)
            total = round(sum(f.est_monthly_savings for f in open_rows), 2)
            scans = repo.list_scans(s)
            return {
                "total_monthly_waste": total,
                "potential_annual_savings": round(total * 12, 2),
                "open_findings": len(open_rows),
                "resources_analyzed": len(resources),
                "by_category": by_category,
                "by_provider": by_provider,
                "top_offenders": [
                    {"resource_id": f.resource_id, "rule": f.rule, "provider": f.provider,
                     "est_monthly_savings": f.est_monthly_savings}
                    for f in open_rows[:5]],
                "scan_trend": [{"scan_id": sc.id, "ran_at": sc.ran_at.isoformat(),
                                "total_savings": sc.total_savings,
                                "finding_count": sc.finding_count} for sc in scans],
            }

    @app.get("/api/scans", response_model=list[ScanOut])
    def scans():
        with repo.session_scope(engine) as s:
            return [ScanOut(id=sc.id, ran_at=sc.ran_at.isoformat(),
                            resource_count=sc.resource_count,
                            finding_count=sc.finding_count,
                            total_savings=sc.total_savings)
                    for sc in repo.list_scans(s)]

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
