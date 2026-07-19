from datetime import datetime, timedelta, timezone
from pathlib import Path

from apps.watchdog.core.alerting import build_alerts
from apps.watchdog.core.bucketing import build_timeline
from apps.watchdog.core.detectors.ewma import ewma_zscore
from apps.watchdog.core.detectors.isolation import isolation_forest
from apps.watchdog.core.engine import run_detectors
from apps.watchdog.core.models import Anomaly
from apps.watchdog.core.parsers.json_log import parse_json

SD = Path(__file__).parents[2] / "sample_data"
T0 = datetime(2026, 7, 19, 10, 0, 0, tzinfo=timezone.utc)


# --- EWMA ---

def test_ewma_flags_spike():
    counts = [1, 0, 1, 2, 1, 0, 1, 30, 1, 0]
    hits = ewma_zscore(counts, threshold=3.0)
    assert any(h["index"] == 7 for h in hits)


def test_ewma_flat_series_clean():
    assert ewma_zscore([2, 2, 2, 2, 2, 2, 2, 2], threshold=3.0) == []


def test_ewma_zero_series_clean():
    assert ewma_zscore([0, 0, 0, 0, 0, 0], threshold=3.0) == []


# --- IsolationForest ---

def test_isolation_flags_spike():
    counts = [1, 0, 1, 2, 1, 0, 1, 30, 1, 0, 1, 2]
    hits = isolation_forest(counts)
    assert any(h["index"] == 7 for h in hits)


def test_isolation_is_deterministic():
    counts = [1, 0, 1, 2, 1, 0, 1, 30, 1, 0, 1, 2]
    assert isolation_forest(counts) == isolation_forest(counts)


def test_isolation_short_or_constant_series():
    assert isolation_forest([1, 2]) == []
    assert isolation_forest([5, 5, 5, 5, 5, 5, 5]) == []


# --- engine ---

def test_engine_min_errors_floor():
    from apps.watchdog.core.models import BucketPoint
    # a lone 1-error blip in a quiet series should not page anyone
    series = [BucketPoint("api", T0 + timedelta(minutes=i), total=5,
                          errors=(1 if i == 5 else 0)) for i in range(10)]
    tl = {"bucket_seconds": 60, "services": {"api": series}}
    assert run_detectors(tl, min_errors=3) == []
    # a real spike (8 errors) is caught
    series[5].errors = 8
    assert len(run_detectors(tl, min_errors=3)) >= 1


def test_engine_on_sample_catches_checkout_spike():
    events, _ = parse_json((SD / "app.log").read_bytes(), "app.log")
    tl = build_timeline(events, 60)
    anoms = run_detectors(tl)
    checkout = [a for a in anoms if a.service == "checkout"]
    assert checkout, "checkout spike should be detected"
    assert max(a.error_count for a in checkout) >= 5
    assert any(a.method == "ewma_zscore" for a in checkout)
    assert any(a.method == "isolation_forest" for a in checkout)


# --- alerting ---

def anom(service, minute, score):
    return Anomaly(service=service, bucket_start=T0 + timedelta(minutes=minute),
                   error_count=10, score=score, method="ewma_zscore",
                   severity="critical")


def test_alert_cooldown_dedups_same_service():
    anoms = [anom("api", 1, 5.0), anom("api", 2, 9.0), anom("api", 3, 6.0)]
    alerts = build_alerts(anoms, bucket_seconds=60, cooldown_buckets=3)
    assert len(alerts) == 1
    assert alerts[0].score == 9.0  # keeps the strongest in the window


def test_alert_separate_services_separate_alerts():
    alerts = build_alerts([anom("api", 1, 5.0), anom("web", 1, 5.0)],
                          bucket_seconds=60, cooldown_buckets=3)
    assert len(alerts) == 2


def test_alert_after_cooldown_fires_again():
    alerts = build_alerts([anom("api", 0, 5.0), anom("api", 10, 5.0)],
                          bucket_seconds=60, cooldown_buckets=3)
    assert len(alerts) == 2


def test_alert_payload_shape():
    alerts = build_alerts([anom("api", 1, 5.0)], bucket_seconds=60)
    p = alerts[0].payload
    assert p["event"] == "watchdog_anomaly" and p["service"] == "api"
    assert "summary" in p and alerts[0].delivered is False  # no webhook = simulated
