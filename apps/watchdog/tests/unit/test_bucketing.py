from datetime import datetime, timezone

from apps.watchdog.core.bucketing import build_timeline
from apps.watchdog.core.models import LogEvent

T0 = datetime(2026, 7, 19, 10, 0, 0, tzinfo=timezone.utc)


def ev(sec, level="info", service="api"):
    return LogEvent(ts=T0.replace(minute=sec // 60, second=sec % 60),
                    level=level, service=service, message="m")


def test_empty_timeline():
    tl = build_timeline([], 60)
    assert tl["services"] == {} and tl["start"] is None


def test_buckets_count_errors_and_totals():
    events = [ev(0, "info"), ev(10, "error"), ev(20, "error"), ev(70, "info")]
    tl = build_timeline(events, 60)
    api = tl["services"]["api"]
    assert len(api) == 2
    assert api[0].total == 3 and api[0].errors == 2
    assert api[1].total == 1 and api[1].errors == 0


def test_gaps_are_zero_filled():
    events = [ev(0, "error", "api"), ev(180, "error", "api")]  # buckets 0 and 3
    tl = build_timeline(events, 60)
    api = tl["services"]["api"]
    assert len(api) == 4  # 0,1,2,3 — gap filled
    assert api[1].total == 0 and api[2].total == 0
    assert api[0].errors == 1 and api[3].errors == 1


def test_multiple_services_share_range():
    events = [ev(0, "info", "api"), ev(180, "info", "web")]
    tl = build_timeline(events, 60)
    assert set(tl["services"]) == {"api", "web"}
    # both series span the full [0, 3] range
    assert len(tl["services"]["api"]) == len(tl["services"]["web"]) == 4
