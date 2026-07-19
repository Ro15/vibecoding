"""Turn anomalies into alerts, with cooldown dedup + a simulated webhook POST.

Nothing here reaches a real cloud/pager unless a webhook URL is configured; by
default an alert is *recorded* with the exact payload a webhook would receive.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import timedelta

from apps.watchdog.core.models import Anomaly


@dataclass
class Alert:
    service: str
    bucket_start: object
    error_count: int
    score: float
    method: str
    severity: str
    payload: dict
    delivered: bool


def _payload(a: Anomaly) -> dict:
    return {
        "event": "watchdog_anomaly",
        "service": a.service,
        "bucket_start": a.bucket_start.isoformat(),
        "error_count": a.error_count,
        "score": a.score,
        "method": a.method,
        "severity": a.severity,
        "summary": f"{a.severity.upper()} error spike in '{a.service}': "
                   f"{a.error_count} errors (score {a.score}, via {a.method}).",
    }


def build_alerts(anomalies: list[Anomaly], bucket_seconds: int = 60,
                 cooldown_buckets: int = 3, webhook_url: str | None = None) -> list[Alert]:
    """One alert per service per cooldown window; keeps the highest-scoring anomaly."""
    cooldown = timedelta(seconds=bucket_seconds * cooldown_buckets)
    last_fired: dict[str, object] = {}
    alerts: list[Alert] = []
    # process strongest first so a window keeps its worst spike
    for a in sorted(anomalies, key=lambda x: -x.score):
        prev = last_fired.get(a.service)
        if prev is not None and abs((a.bucket_start - prev)) < cooldown:
            continue
        last_fired[a.service] = a.bucket_start
        payload = _payload(a)
        delivered = _deliver(webhook_url, payload) if webhook_url else False
        alerts.append(Alert(service=a.service, bucket_start=a.bucket_start,
                            error_count=a.error_count, score=a.score, method=a.method,
                            severity=a.severity, payload=payload, delivered=delivered))
    alerts.sort(key=lambda x: x.bucket_start)
    return alerts


def _deliver(url: str, payload: dict) -> bool:
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
        return True
    except OSError:
        return False
