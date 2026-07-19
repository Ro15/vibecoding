"""Per-endpoint E2E tests for Watchdog."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.watchdog.api.main import create_app

SD = Path(__file__).parents[2] / "sample_data"


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "w.db"))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def ingest(client, name, fmt):
    with open(SD / name, "rb") as f:
        return client.post("/api/ingest", files={"file": (name, f)}, data={"format": fmt})


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_ingest_json_detects_spike(client):
    r = ingest(client, "app.log", "json")
    assert r.status_code == 200
    b = r.json()
    assert b["event_count"] == 431
    assert b["service_count"] == 3
    assert b["anomaly_count"] >= 2
    assert b["alert_count"] >= 1
    assert b["parse_errors"] == []


def test_ingest_syslog(client):
    b = ingest(client, "platform.log", "syslog").json()
    assert b["source_format"] == "syslog"
    assert b["anomaly_count"] >= 1


def test_ingest_unknown_format_422(client):
    with open(SD / "app.log", "rb") as f:
        r = client.post("/api/ingest", files={"file": ("x", f)}, data={"format": "xml"})
    assert r.status_code == 422


def test_ingest_garbage_422(client):
    r = client.post("/api/ingest", files={"file": ("x", b"not a log at all")},
                    data={"format": "json"})
    assert r.status_code == 422


def test_health_timeline(client):
    ingest(client, "app.log", "json")
    h = client.get("/api/health").json()
    assert h["bucket_seconds"] == 60
    svcs = {s["service"] for s in h["services"]}
    assert svcs == {"api", "checkout", "worker"}
    checkout = next(s for s in h["services"] if s["service"] == "checkout")
    assert len(checkout["points"]) > 5
    assert len(checkout["anomalies"]) >= 1
    assert len(h["overall"]) > 5


def test_anomalies_endpoint(client):
    ingest(client, "app.log", "json")
    anoms = client.get("/api/anomalies").json()
    assert any(a["service"] == "checkout" for a in anoms)
    assert all(a["method"] in ("ewma_zscore", "isolation_forest") for a in anoms)


def test_alerts_endpoint(client):
    ingest(client, "app.log", "json")
    alerts = client.get("/api/alerts").json()
    assert len(alerts) >= 1
    a = alerts[0]
    assert a["summary"] and a["delivered"] is False  # simulated (no webhook set)
    assert a["severity"] in ("critical", "high", "medium")


def test_summary(client):
    ingest(client, "app.log", "json")
    s = client.get("/api/summary").json()
    assert s["event_count"] == 431
    assert s["service_count"] == 3
    assert 0 <= s["error_rate"] <= 1
    assert s["worst_service"] == "checkout"
    assert "ewma_zscore" in s["by_method"] or "isolation_forest" in s["by_method"]


def test_summary_empty(client):
    s = client.get("/api/summary").json()
    assert s["event_count"] == 0 and s["anomaly_count"] == 0


def test_config_roundtrip(client):
    c = client.get("/api/config").json()
    assert c["ewma_threshold"] == 3.0 and c["bucket_seconds"] == 60
    r = client.put("/api/config", json={"ewma_threshold": 5.0, "webhook_url": "http://x"})
    assert r.status_code == 200
    assert r.json()["ewma_threshold"] == 5.0 and r.json()["webhook_url"] == "http://x"


def test_config_threshold_changes_detection(client):
    ingest(client, "app.log", "json")
    base = client.get("/api/summary").json()["anomaly_count"]
    client.put("/api/config", json={"ewma_threshold": 50.0})  # very strict
    ingest(client, "app.log", "json")
    stricter = client.get("/api/summary").json()["anomaly_count"]
    assert stricter <= base  # fewer ewma anomalies at a high threshold


def test_latest_ingest_drives_views(client):
    ingest(client, "app.log", "json")
    ingest(client, "platform.log", "syslog")  # newest
    s = client.get("/api/summary").json()
    assert s["source_format"] == "syslog"
    assert client.get("/api/ingests").json().__len__() == 2


def test_dashboard_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
