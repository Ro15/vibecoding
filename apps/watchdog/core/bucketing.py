"""Turn a flat LogEvent stream into per-service, gap-filled time buckets.

Single pass over events (O(N)); output is O(services x buckets), independent of N
beyond the pass — the property that lets detection stay memory-bounded.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from apps.watchdog.core.models import BucketPoint, LogEvent, is_error


def _floor(ts: datetime, size: int) -> datetime:
    epoch = int(ts.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % size), tz=ts.tzinfo)


def build_timeline(events: list[LogEvent], bucket_seconds: int = 60) -> dict:
    """Return {bucket_seconds, start, end, services: {svc: [BucketPoint,...]}}.

    Each service series spans the full [start, end] range with zero-filled gaps so
    the health trend and detectors see a continuous signal.
    """
    if not events:
        return {"bucket_seconds": bucket_seconds, "start": None, "end": None, "services": {}}

    counts: dict[tuple, list[int]] = {}  # (service, bucket_start) -> [total, errors]
    services = set()
    min_b = max_b = _floor(events[0].ts, bucket_seconds)
    for ev in events:
        b = _floor(ev.ts, bucket_seconds)
        services.add(ev.service)
        key = (ev.service, b)
        rec = counts.setdefault(key, [0, 0])
        rec[0] += 1
        if is_error(ev.level):
            rec[1] += 1
        min_b = min(min_b, b)
        max_b = max(max_b, b)

    step = timedelta(seconds=bucket_seconds)
    timeline = {}
    for svc in sorted(services):
        series = []
        b = min_b
        while b <= max_b:
            total, errors = counts.get((svc, b), [0, 0])
            series.append(BucketPoint(service=svc, bucket_start=b, total=total, errors=errors))
            b += step
        timeline[svc] = series
    return {"bucket_seconds": bucket_seconds, "start": min_b, "end": max_b,
            "services": timeline}
