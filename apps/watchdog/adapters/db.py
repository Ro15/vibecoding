"""Watchdog SQLite repository, built on common.db."""
from __future__ import annotations

import json

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from apps.watchdog.adapters.orm import (AlertRow, AnomalyRow, Base, Bucket, Config,
                                        Ingest)
from apps.watchdog.core.alerting import Alert
from apps.watchdog.core.models import Anomaly
from common.db import init_engine, session_scope  # noqa: F401  (re-exported)

CONFIG_DEFAULTS = {"webhook_url": "", "ewma_threshold": "3.0", "bucket_seconds": "60"}


def init_db(path: str):
    return init_engine(path, Base.metadata)


def get_config(session: Session) -> dict:
    stored = {c.key: c.value for c in session.scalars(select(Config))}
    return {**CONFIG_DEFAULTS, **stored}


def set_config(session: Session, updates: dict) -> dict:
    for key, value in updates.items():
        if key not in CONFIG_DEFAULTS:
            raise ValueError(f"unknown config key {key!r}")
        row = session.get(Config, key)
        if row is None:
            session.add(Config(key=key, value=str(value)))
        else:
            row.value = str(value)
    session.flush()
    return get_config(session)


def record_ingest(session: Session, source: str, source_format: str, event_count: int,
                  bucket_seconds: int, timeline: dict, anomalies: list[Anomaly],
                  alerts: list[Alert]) -> Ingest:
    ingest = Ingest(source=source, source_format=source_format, event_count=event_count,
                    bucket_seconds=bucket_seconds)
    session.add(ingest)
    session.flush()
    for series in timeline.get("services", {}).values():
        for p in series:
            session.add(Bucket(ingest_id=ingest.id, service=p.service,
                               bucket_start=p.bucket_start, total=p.total, errors=p.errors))
    for a in anomalies:
        session.add(AnomalyRow(ingest_id=ingest.id, service=a.service,
                               bucket_start=a.bucket_start, error_count=a.error_count,
                               score=a.score, method=a.method, severity=a.severity))
    for al in alerts:
        session.add(AlertRow(ingest_id=ingest.id, service=al.service,
                             bucket_start=al.bucket_start, error_count=al.error_count,
                             score=al.score, method=al.method, severity=al.severity,
                             payload_json=json.dumps(al.payload), delivered=al.delivered))
    session.flush()
    return ingest


def latest_ingest(session: Session) -> Ingest | None:
    return session.scalar(select(Ingest).order_by(Ingest.id.desc()).limit(1))


def list_ingests(session: Session) -> list[Ingest]:
    return list(session.scalars(select(Ingest).order_by(Ingest.id)))


def buckets_for(session: Session, ingest_id: int) -> list[Bucket]:
    return list(session.scalars(
        select(Bucket).where(Bucket.ingest_id == ingest_id).order_by(Bucket.bucket_start)))


def anomalies_for(session: Session, ingest_id: int) -> list[AnomalyRow]:
    return list(session.scalars(
        select(AnomalyRow).where(AnomalyRow.ingest_id == ingest_id)
        .order_by(AnomalyRow.bucket_start)))


def alerts_for(session: Session, ingest_id: int) -> list[AlertRow]:
    return list(session.scalars(
        select(AlertRow).where(AlertRow.ingest_id == ingest_id)
        .order_by(AlertRow.bucket_start)))
