"""Watchdog FastAPI adapter, built on common.api."""
from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

from fastapi import File, Form, HTTPException, UploadFile

from apps.watchdog.adapters import db as repo
from apps.watchdog.core.alerting import build_alerts
from apps.watchdog.core.bucketing import build_timeline
from apps.watchdog.core.engine import run_detectors
from apps.watchdog.core.models import is_error  # noqa: F401
from apps.watchdog.core.registry import all_parsers, get_parser
from apps.watchdog.api.schemas import (AlertOut, AnomalyOut, ConfigModel,
                                       IngestResponse)
from common.api import make_app, mount_dashboard

STATIC_DIR = Path(__file__).parents[1] / "static"
FORMAT_HINTS = {"json": "app.log", "syslog": "platform.log", "text": "app.log"}


def create_app(db_path: str = "watchdog.db"):
    app = make_app("Intelligent Observability & Event Watchdog",
                   "Parse logs, detect error spikes, trigger simulated webhook alerts.",
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
            events, errors = get_parser(format)(content, filename)
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        with repo.session_scope(engine) as s:
            cfg = repo.get_config(s)
            bucket_seconds = int(cfg["bucket_seconds"])
            timeline = build_timeline(events, bucket_seconds)
            anomalies = run_detectors(timeline, ewma_threshold=float(cfg["ewma_threshold"]))
            alerts = build_alerts(anomalies, bucket_seconds=bucket_seconds,
                                  webhook_url=(cfg["webhook_url"] or None))
            ingest_row = repo.record_ingest(s, filename, format, len(events),
                                            bucket_seconds, timeline, anomalies, alerts)
            return IngestResponse(
                source=filename, source_format=format, event_count=len(events),
                parse_errors=errors[:50], ingest_id=ingest_row.id,
                service_count=len(timeline.get("services", {})),
                anomaly_count=len(anomalies), alert_count=len(alerts),
                bucket_seconds=bucket_seconds)

    @app.get("/api/health")
    def health_timeline():
        with repo.session_scope(engine) as s:
            latest = repo.latest_ingest(s)
            if latest is None:
                return {"bucket_seconds": 60, "services": [], "overall": []}
            buckets = repo.buckets_for(s, latest.id)
            anoms = repo.anomalies_for(s, latest.id)
            anom_by_svc: dict[str, list] = defaultdict(list)
            for a in anoms:
                anom_by_svc[a.service].append(
                    {"t": a.bucket_start.isoformat(), "score": a.score,
                     "method": a.method, "severity": a.severity,
                     "error_count": a.error_count})
            by_svc: dict[str, list] = defaultdict(list)
            overall: dict[str, dict] = {}
            for b in buckets:
                t = b.bucket_start.isoformat()
                by_svc[b.service].append({"t": t, "total": b.total, "errors": b.errors})
                o = overall.setdefault(t, {"t": t, "total": 0, "errors": 0})
                o["total"] += b.total
                o["errors"] += b.errors
            services = [{"service": svc, "points": pts,
                         "anomalies": anom_by_svc.get(svc, [])}
                        for svc, pts in sorted(by_svc.items())]
            return {"bucket_seconds": latest.bucket_seconds, "services": services,
                    "overall": [overall[k] for k in sorted(overall)]}

    @app.get("/api/anomalies", response_model=list[AnomalyOut])
    def anomalies():
        with repo.session_scope(engine) as s:
            latest = repo.latest_ingest(s)
            if latest is None:
                return []
            return [AnomalyOut(service=a.service, bucket_start=a.bucket_start.isoformat(),
                               error_count=a.error_count, score=a.score, method=a.method,
                               severity=a.severity)
                    for a in repo.anomalies_for(s, latest.id)]

    @app.get("/api/alerts", response_model=list[AlertOut])
    def alerts():
        with repo.session_scope(engine) as s:
            latest = repo.latest_ingest(s)
            if latest is None:
                return []
            out = []
            for a in repo.alerts_for(s, latest.id):
                payload = json.loads(a.payload_json)
                out.append(AlertOut(id=a.id, service=a.service,
                                    bucket_start=a.bucket_start.isoformat(),
                                    error_count=a.error_count, score=a.score,
                                    method=a.method, severity=a.severity,
                                    delivered=a.delivered,
                                    summary=payload.get("summary", "")))
            return out

    @app.get("/api/summary")
    def summary():
        with repo.session_scope(engine) as s:
            latest = repo.latest_ingest(s)
            if latest is None:
                return {"event_count": 0, "service_count": 0, "error_rate": 0.0,
                        "anomaly_count": 0, "alert_count": 0, "source": None,
                        "by_service": {}, "by_method": {}, "worst_service": None}
            buckets = repo.buckets_for(s, latest.id)
            anoms = repo.anomalies_for(s, latest.id)
            alerts_rows = repo.alerts_for(s, latest.id)
            total = sum(b.total for b in buckets)
            errs = sum(b.errors for b in buckets)
            by_service: dict[str, int] = defaultdict(int)
            for b in buckets:
                by_service[b.service] += b.errors
            by_method: dict[str, int] = defaultdict(int)
            for a in anoms:
                by_method[a.method] += 1
            worst = max(by_service.items(), key=lambda kv: kv[1], default=(None, 0))
            return {
                "event_count": latest.event_count,
                "service_count": len({b.service for b in buckets}),
                "error_rate": round(errs / total, 4) if total else 0.0,
                "anomaly_count": len(anoms), "alert_count": len(alerts_rows),
                "source": latest.source, "source_format": latest.source_format,
                "by_service": dict(by_service), "by_method": dict(by_method),
                "worst_service": worst[0],
            }

    @app.get("/api/config")
    def get_config():
        with repo.session_scope(engine) as s:
            c = repo.get_config(s)
            return {"webhook_url": c["webhook_url"],
                    "ewma_threshold": float(c["ewma_threshold"]),
                    "bucket_seconds": int(c["bucket_seconds"])}

    @app.put("/api/config")
    def put_config(body: ConfigModel):
        updates = {}
        if body.webhook_url is not None:
            updates["webhook_url"] = body.webhook_url
        if body.ewma_threshold is not None:
            updates["ewma_threshold"] = body.ewma_threshold
        if body.bucket_seconds is not None:
            updates["bucket_seconds"] = body.bucket_seconds
        with repo.session_scope(engine) as s:
            try:
                c = repo.set_config(s, updates)
            except ValueError as exc:
                raise HTTPException(422, detail=str(exc)) from exc
            return {"webhook_url": c["webhook_url"],
                    "ewma_threshold": float(c["ewma_threshold"]),
                    "bucket_seconds": int(c["bucket_seconds"])}

    @app.get("/api/ingests")
    def ingests():
        with repo.session_scope(engine) as s:
            return [{"id": i.id, "ran_at": i.ran_at.isoformat(), "source": i.source,
                     "source_format": i.source_format, "event_count": i.event_count}
                    for i in repo.list_ingests(s)]

    mount_dashboard(app, STATIC_DIR)
    return app


app = create_app(os.environ.get("WATCHDOG_DB", "watchdog.db"))
