"""Pydantic response models for Watchdog."""
from __future__ import annotations

from pydantic import BaseModel


class IngestResponse(BaseModel):
    source: str
    source_format: str
    event_count: int
    parse_errors: list[dict]
    ingest_id: int
    service_count: int
    anomaly_count: int
    alert_count: int
    bucket_seconds: int


class AlertOut(BaseModel):
    id: int
    service: str
    bucket_start: str
    error_count: int
    score: float
    method: str
    severity: str
    delivered: bool
    summary: str


class AnomalyOut(BaseModel):
    service: str
    bucket_start: str
    error_count: int
    score: float
    method: str
    severity: str


class ConfigModel(BaseModel):
    webhook_url: str | None = None
    ewma_threshold: float | None = None
    bucket_seconds: int | None = None
