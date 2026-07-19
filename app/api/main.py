"""FastAPI adapter — thin shell over the core domain."""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.adapters import db as repo
from app.core import engine as rules_engine
import app.core.providers  # noqa: F401  (registers aws/azure/gcp/focus parsers)
from app.core.execution import DEFAULT_EXECUTOR
from app.core.models import FindingResult, NormalizedResource
from app.core.registry import all_providers, get_provider
from app.core.remediation import build_plan, render_script
from app.api.schemas import (AnalyzeResponse, ExecuteRequest, ExecutionOut,
                             FindingOut, IngestResponse, RemediationOut,
                             ScanOut, SchedulePut, StatusPatch)

STATIC_DIR = Path(__file__).parents[1] / "static"

SCHEDULE_KEYS = ("schedule_enabled", "schedule_interval_minutes", "webhook_url")


def _finding_to_result(row) -> FindingResult:
    """Rehydrate a stored finding into a core FindingResult for remediation."""
    return FindingResult(
        resource=NormalizedResource(
            provider=row.provider, resource_id=row.resource_id,
            resource_type=row.resource_type, region=row.region,
            billing_period="", monthly_cost=row.est_monthly_savings,
            usage_hours=0.0, state="", created_at=None,
            tags={"owner": row.owner} if row.owner else {}),
        rule=row.rule, category=row.category, severity=row.severity,
        est_monthly_savings=row.est_monthly_savings, reason=row.reason)


def create_app(db_path: str = "costopt.db", viewer_key: str | None = None,
               operator_key: str | None = None) -> FastAPI:
    app = FastAPI(title="Cloud Cost Optimizer & Remediation Engine",
                  description="FinOps API: ingest billing exports, detect orphaned "
                              "resources, generate decommission commands.",
                  version="1.1.0")
    engine = repo.init_db(db_path)
    viewer_key = viewer_key or os.environ.get("COSTOPT_VIEWER_KEY")
    operator_key = operator_key or os.environ.get("COSTOPT_OPERATOR_KEY")
    app.state.scheduler = None

    # --- auth ---
    def _check(role: str, x_api_key: str | None):
        if not viewer_key and not operator_key:
            return "anonymous"  # auth disabled (local mode)
        if x_api_key is None:
            raise HTTPException(401, detail="missing X-API-Key header")
        if role == "operator":
            if x_api_key == operator_key:
                return "operator"
            raise HTTPException(403, detail="operator key required")
        if x_api_key in {viewer_key, operator_key}:
            return "operator" if x_api_key == operator_key else "viewer"
        raise HTTPException(403, detail="invalid API key")

    def require(role: str):
        def dep(x_api_key: str | None = Header(default=None)):
            return _check(role, x_api_key)
        return Depends(dep)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        return JSONResponse(status_code=500,
                            content={"error": {"message": str(exc), "details": None}})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # --- ingest ---
    @app.post("/api/ingest", response_model=IngestResponse)
    async def ingest(file: UploadFile = File(...), provider: str = Form(...),
                     _actor: str = require("operator")):
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

    # --- analyze (latest billing period = "current waste") ---
    def _run_scan(session) -> AnalyzeResponse:
        rows = repo.list_resources(session)
        resources = [repo.to_normalized(r) for r in rows]
        periods = sorted({r.billing_period for r in resources})
        current = [r for r in resources if not periods or r.billing_period == periods[-1]]
        policies = repo.get_policies(session)
        results = rules_engine.run_rules(current, policies=policies)
        scan = repo.create_scan(session, resource_count=len(current))
        stats = repo.apply_findings(session, scan, results)
        return AnalyzeResponse(scan_id=scan.id, resource_count=len(current),
                               findings_new=stats["new"], findings_updated=stats["updated"],
                               findings_stale=stats["stale"],
                               open_findings=scan.finding_count,
                               total_est_monthly_savings=scan.total_savings)

    @app.post("/api/analyze", response_model=AnalyzeResponse)
    def analyze(_actor: str = require("operator")):
        with repo.session_scope(engine) as s:
            return _run_scan(s)

    # --- findings ---
    @app.get("/api/findings", response_model=list[FindingOut])
    def findings(provider: str | None = None, rule: str | None = None,
                 status: str | None = None, min_savings: float | None = None,
                 _actor: str = require("viewer")):
        with repo.session_scope(engine) as s:
            rows = repo.list_findings(s, provider=provider, rule=rule,
                                      status=status, min_savings=min_savings)
            return [FindingOut.model_validate(r, from_attributes=True) for r in rows]

    @app.patch("/api/findings/{finding_id}", response_model=FindingOut)
    def patch_finding(finding_id: int, body: StatusPatch,
                      _actor: str = require("operator")):
        with repo.session_scope(engine) as s:
            try:
                row = repo.set_finding_status(s, finding_id, body.status)
            except KeyError as exc:
                raise HTTPException(404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(422, detail=str(exc)) from exc
            return FindingOut.model_validate(row, from_attributes=True)

    @app.get("/api/findings/{finding_id}/remediation", response_model=RemediationOut)
    def remediation(finding_id: int, _actor: str = require("viewer")):
        with repo.session_scope(engine) as s:
            try:
                row = repo.get_finding(s, finding_id)
            except KeyError as exc:
                raise HTTPException(404, detail=str(exc)) from exc
            plan = build_plan(_finding_to_result(row))
            return RemediationOut(finding_id=row.id, rule=plan.rule, provider=plan.provider,
                                  resource_id=plan.resource_id,
                                  steps=[vars(step) for step in plan.steps])

    # --- guarded (simulated) execution ---
    @app.post("/api/findings/{finding_id}/execute", response_model=ExecutionOut)
    def execute(finding_id: int, body: ExecuteRequest,
                actor: str = require("operator")):
        if not body.dry_run and not body.approve:
            raise HTTPException(422, detail="non-dry-run execution requires approve=true")
        with repo.session_scope(engine) as s:
            try:
                row = repo.get_finding(s, finding_id)
            except KeyError as exc:
                raise HTTPException(404, detail=str(exc)) from exc
            if row.status not in ("open", "stale"):
                raise HTTPException(422, detail=f"finding is {row.status}; only open/stale "
                                                f"findings can be executed")
            plan = build_plan(_finding_to_result(row))
            result = DEFAULT_EXECUTOR.execute(plan, dry_run=body.dry_run)
            record = repo.record_execution(s, row.id, actor, DEFAULT_EXECUTOR.name,
                                           result.dry_run, result.commands,
                                           result.output, result.succeeded)
            if not body.dry_run and result.succeeded:
                repo.set_finding_status(s, row.id, "remediated")
            return ExecutionOut(id=record.id, finding_id=row.id, actor=record.actor,
                                executor=record.executor, dry_run=record.dry_run,
                                commands=result.commands, output=record.output,
                                succeeded=record.succeeded,
                                executed_at=record.executed_at.isoformat())

    @app.get("/api/executions", response_model=list[ExecutionOut])
    def executions(_actor: str = require("viewer")):
        with repo.session_scope(engine) as s:
            return [ExecutionOut(id=e.id, finding_id=e.finding_id, actor=e.actor,
                                 executor=e.executor, dry_run=e.dry_run,
                                 commands=json.loads(e.commands_json), output=e.output,
                                 succeeded=e.succeeded,
                                 executed_at=e.executed_at.isoformat())
                    for e in repo.list_executions(s)]

    # --- remediation script ---
    @app.get("/api/remediation/script")
    def remediation_script(provider: str, _actor: str = require("viewer")):
        if provider not in ("aws", "azure", "gcp"):
            raise HTTPException(422, detail=f"unknown provider {provider!r}")
        with repo.session_scope(engine) as s:
            rows = repo.list_findings(s, provider=provider, status="open")
            script = render_script([(r.id, _finding_to_result(r)) for r in rows], provider)
            return PlainTextResponse(script, media_type="text/x-shellscript",
                                     headers={"Content-Disposition":
                                              f"attachment; filename=remediate_{provider}.sh"})

    # --- policies ---
    @app.get("/api/policies")
    def get_policies(_actor: str = require("viewer")):
        with repo.session_scope(engine) as s:
            return repo.get_policies(s)

    @app.put("/api/policies")
    def put_policies(body: dict, _actor: str = require("operator")):
        with repo.session_scope(engine) as s:
            try:
                return repo.set_policies(s, body)
            except ValueError as exc:
                raise HTTPException(422, detail=str(exc)) from exc

    # --- schedule ---
    def _build_digest(session) -> dict:
        summary = _summary_data(session)
        return {"event": "costopt_scan_digest",
                "open_findings": summary["open_findings"],
                "total_monthly_waste": summary["total_monthly_waste"],
                "realized_monthly_savings": summary["realized_monthly_savings"],
                "by_provider": summary["by_provider"]}

    def _scan_job():
        with repo.session_scope(engine) as s:
            _run_scan(s)
            policies = repo.get_policies(s)
            url = str(policies.get("webhook_url") or "")
            if url:
                payload = json.dumps(_build_digest(s)).encode()
                req = urllib.request.Request(url, data=payload,
                                             headers={"Content-Type": "application/json"})
                try:
                    urllib.request.urlopen(req, timeout=10)
                except OSError:
                    pass  # digest delivery is best-effort

    app.state.scan_job = _scan_job  # exposed for tests

    def _apply_schedule(policies: dict):
        enabled = int(policies["schedule_enabled"])
        interval = max(1, int(policies["schedule_interval_minutes"]))
        sched = app.state.scheduler
        if enabled:
            if sched is None:
                from apscheduler.schedulers.background import BackgroundScheduler
                sched = BackgroundScheduler(daemon=True)
                sched.start()
                app.state.scheduler = sched
            for job in sched.get_jobs():
                job.remove()
            sched.add_job(_scan_job, "interval", minutes=interval, id="costopt-scan")
        elif sched is not None:
            for job in sched.get_jobs():
                job.remove()

    @app.get("/api/schedule")
    def get_schedule(_actor: str = require("viewer")):
        with repo.session_scope(engine) as s:
            p = repo.get_policies(s)
            jobs = (app.state.scheduler.get_jobs() if app.state.scheduler else [])
            return {"enabled": bool(int(p["schedule_enabled"])),
                    "interval_minutes": int(p["schedule_interval_minutes"]),
                    "webhook_url": p["webhook_url"],
                    "job_active": len(jobs) > 0}

    @app.put("/api/schedule")
    def put_schedule(body: SchedulePut, _actor: str = require("operator")):
        with repo.session_scope(engine) as s:
            updates = {"schedule_enabled": int(body.enabled),
                       "schedule_interval_minutes": body.interval_minutes}
            if body.webhook_url is not None:
                updates["webhook_url"] = body.webhook_url
            policies = repo.set_policies(s, updates)
        _apply_schedule(policies)
        return {"enabled": bool(int(policies["schedule_enabled"])),
                "interval_minutes": int(policies["schedule_interval_minutes"]),
                "webhook_url": policies["webhook_url"],
                "job_active": bool(app.state.scheduler and app.state.scheduler.get_jobs())}

    # --- summary / trends / scans ---
    def _summary_data(session) -> dict:
        open_rows = repo.list_findings(session, status="open")
        remediated = repo.list_findings(session, status="remediated")
        resources = repo.list_resources(session)
        by_category: dict[str, float] = {}
        by_provider: dict[str, float] = {}
        by_owner: dict[str, float] = {}
        for f in open_rows:
            by_category[f.category] = round(by_category.get(f.category, 0) + f.est_monthly_savings, 2)
            by_provider[f.provider] = round(by_provider.get(f.provider, 0) + f.est_monthly_savings, 2)
            owner = f.owner or "(untagged)"
            by_owner[owner] = round(by_owner.get(owner, 0) + f.est_monthly_savings, 2)
        total = round(sum(f.est_monthly_savings for f in open_rows), 2)
        realized = round(sum(f.realized_monthly_savings for f in remediated), 2)
        scans = repo.list_scans(session)
        return {
            "total_monthly_waste": total,
            "potential_annual_savings": round(total * 12, 2),
            "open_findings": len(open_rows),
            "resources_analyzed": len(resources),
            "realized_monthly_savings": realized,
            "by_category": by_category,
            "by_provider": by_provider,
            "by_owner": dict(sorted(by_owner.items(), key=lambda kv: -kv[1])[:6]),
            "top_offenders": [
                {"resource_id": f.resource_id, "rule": f.rule, "provider": f.provider,
                 "owner": f.owner, "est_monthly_savings": f.est_monthly_savings}
                for f in open_rows[:5]],
            "scan_trend": [{"scan_id": sc.id, "ran_at": sc.ran_at.isoformat(),
                            "total_savings": sc.total_savings,
                            "finding_count": sc.finding_count} for sc in scans],
        }

    @app.get("/api/summary")
    def summary(_actor: str = require("viewer")):
        with repo.session_scope(engine) as s:
            return _summary_data(s)

    @app.get("/api/trends")
    def trends(_actor: str = require("viewer")):
        with repo.session_scope(engine) as s:
            resources = [repo.to_normalized(r) for r in repo.list_resources(s)]
            policies = repo.get_policies(s)
            by_period: dict[str, list] = {}
            for r in resources:
                by_period.setdefault(r.billing_period, []).append(r)
            out = []
            for period in sorted(by_period):
                results = rules_engine.run_rules(by_period[period], policies=policies)
                prov: dict[str, float] = {}
                for f in results:
                    prov[f.resource.provider] = round(
                        prov.get(f.resource.provider, 0) + f.est_monthly_savings, 2)
                out.append({"period": period,
                            "waste": round(sum(f.est_monthly_savings for f in results), 2),
                            "findings": len(results),
                            "by_provider": prov,
                            "resources": len(by_period[period])})
            return {"periods": out}

    @app.get("/api/scans", response_model=list[ScanOut])
    def scans(_actor: str = require("viewer")):
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


app = create_app(os.environ.get("COSTOPT_DB", "costopt.db"))
