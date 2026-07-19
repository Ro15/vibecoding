"""Watchdog domain models. Pure Python."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

ERROR_LEVELS = {"error", "err", "fatal", "critical", "crit", "emerg", "alert", "panic"}


def is_error(level: str) -> bool:
    return (level or "").lower() in ERROR_LEVELS


@dataclass
class LogEvent:
    ts: datetime
    level: str
    service: str
    message: str


@dataclass
class BucketPoint:
    service: str
    bucket_start: datetime
    total: int
    errors: int


@dataclass
class Anomaly:
    service: str
    bucket_start: datetime
    error_count: int
    score: float
    method: str
    severity: str


def severity_for_score(score: float) -> str:
    if score >= 6:
        return "critical"
    if score >= 4:
        return "high"
    return "medium"
