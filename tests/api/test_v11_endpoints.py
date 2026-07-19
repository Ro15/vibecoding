"""API E2E tests for the v1.1 endpoints: gcp/focus ingest, trends, policies,
execution, schedule, and auth."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app

ROOT = Path(__file__).parents[2]
AWS = ROOT / "sample_data" / "aws_cur.csv"
AWS_PREV = ROOT / "sample_data" / "aws_cur_prev.csv"
AZURE = ROOT / "sample_data" / "azure_costs.json"
AZURE_PREV = ROOT / "sample_data" / "azure_costs_prev.json"
GCP = ROOT / "sample_data" / "gcp_billing.json"
FOCUS = ROOT / "sample_data" / "focus_costs.csv"


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "api.db"))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def ingest(client, path: Path, provider: str, **kw):
    with open(path, "rb") as f:
        return client.post("/api/ingest", files={"file": (path.name, f)},
                           data={"provider": provider}, **kw)


# --- GCP + FOCUS ingestion ---

def test_gcp_ingest_and_analyze(client):
    r = ingest(client, GCP, "gcp")
    assert r.status_code == 200
    assert r.json()["rows_ok"] == 12
    body = client.post("/api/analyze").json()
    assert body["open_findings"] == 6
    rules = {f["rule"] for f in client.get("/api/findings").json()}
    assert rules == {"unattached_disk", "idle_vm", "orphaned_ip", "old_snapshot",
                     "oversized_vm", "untagged_resource"}


def test_all_three_providers_together(client):
    for path, prov in ((AWS, "aws"), (AZURE, "azure"), (GCP, "gcp")):
        assert ingest(client, path, prov).status_code == 200
    body = client.post("/api/analyze").json()
    assert body["open_findings"] == 40
    assert body["resource_count"] == 123


def test_focus_ingest_maps_providers(client):
    r = ingest(client, FOCUS, "focus")
    assert r.status_code == 200
    assert r.json()["rows_ok"] == 6
    body = client.post("/api/analyze").json()
    assert body["open_findings"] == 4  # unattached vol, old snap, stopped vm, orphan ip
    providers = {f["provider"] for f in client.get("/api/findings").json()}
    assert providers == {"aws", "azure", "gcp"}


def test_gcp_remediation_script(client):
    ingest(client, GCP, "gcp")
    client.post("/api/analyze")
    r = client.get("/api/remediation/script", params={"provider": "gcp"})
    assert r.status_code == 200
    assert "gcloud compute disks delete" in r.text


# --- trends ---

def test_trends_two_periods(client):
    for path, prov in ((AWS, "aws"), (AWS_PREV, "aws"),
                       (AZURE, "azure"), (AZURE_PREV, "azure")):
        assert ingest(client, path, prov).status_code == 200
    t = client.get("/api/trends").json()
    periods = {p["period"]: p for p in t["periods"]}
    assert set(periods) == {"2026-05", "2026-06"}
    assert periods["2026-06"]["waste"] > periods["2026-05"]["waste"] > 0
    assert periods["2026-05"]["by_provider"].keys() == {"aws", "azure"}


def test_analyze_scans_latest_period_only(client):
    ingest(client, AWS, "aws")
    ingest(client, AWS_PREV, "aws")
    body = client.post("/api/analyze").json()
    assert body["resource_count"] == 64  # June only, not 64+13


# --- policies ---

def test_policies_get_defaults(client):
    p = client.get("/api/policies").json()
    assert p["snapshot_retention_days"] == 90
    assert p["cpu_idle_threshold_pct"] == 3.0


def test_policies_put_changes_detection(client):
    ingest(client, AWS, "aws")
    base = client.post("/api/analyze").json()["open_findings"]
    # loosen retention beyond snapshot age → old_snapshot findings vanish
    r = client.put("/api/policies", json={"snapshot_retention_days": 100000})
    assert r.status_code == 200 and r.json()["snapshot_retention_days"] == 100000
    body = client.post("/api/analyze").json()
    assert body["open_findings"] == base - 3
    assert client.put("/api/policies", json={"nope": 1}).status_code == 422


# --- realization ---

def test_remediated_finding_updates_realized_total(client):
    ingest(client, AWS, "aws")
    client.post("/api/analyze")
    f = client.get("/api/findings").json()[0]
    client.patch(f"/api/findings/{f['id']}", json={"status": "remediated"})
    s = client.get("/api/summary").json()
    assert s["realized_monthly_savings"] == f["est_monthly_savings"]
    updated = client.get("/api/findings", params={"status": "remediated"}).json()[0]
    assert updated["remediated_at"] is not None


def test_summary_by_owner(client):
    ingest(client, AWS, "aws")
    client.post("/api/analyze")
    s = client.get("/api/summary").json()
    assert "team-platform" in s["by_owner"]
    assert "(untagged)" in s["by_owner"]


# --- guarded execution ---

def test_execute_dry_run(client):
    ingest(client, AWS, "aws")
    client.post("/api/analyze")
    fid = client.get("/api/findings").json()[0]["id"]
    r = client.post(f"/api/findings/{fid}/execute", json={"dry_run": True})
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True and body["succeeded"] is True
    assert "[dry-run]" in body["output"] and "DESTRUCTIVE" in body["output"]
    # dry run does NOT change status
    assert client.get("/api/findings").json()[0]["status"] == "open"


def test_execute_requires_approval(client):
    ingest(client, AWS, "aws")
    client.post("/api/analyze")
    fid = client.get("/api/findings").json()[0]["id"]
    r = client.post(f"/api/findings/{fid}/execute",
                    json={"dry_run": False, "approve": False})
    assert r.status_code == 422


def test_execute_approved_marks_remediated_and_audits(client):
    ingest(client, AWS, "aws")
    client.post("/api/analyze")
    f = client.get("/api/findings").json()[0]
    r = client.post(f"/api/findings/{f['id']}/execute",
                    json={"dry_run": False, "approve": True})
    assert r.status_code == 200
    assert r.json()["dry_run"] is False
    updated = next(x for x in client.get("/api/findings").json() if x["id"] == f["id"])
    assert updated["status"] == "remediated"
    assert updated["realized_monthly_savings"] == f["est_monthly_savings"]
    # re-execution of a remediated finding is rejected
    assert client.post(f"/api/findings/{f['id']}/execute",
                       json={"dry_run": False, "approve": True}).status_code == 422
    audits = client.get("/api/executions").json()
    assert len(audits) == 1 and audits[0]["finding_id"] == f["id"]
    assert client.post("/api/findings/99999/execute", json={}).status_code == 404


# --- schedule ---

def test_schedule_roundtrip_and_job(client):
    s = client.get("/api/schedule").json()
    assert s["enabled"] is False and s["job_active"] is False
    r = client.put("/api/schedule", json={"enabled": True, "interval_minutes": 999,
                                          "webhook_url": ""})
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True and body["job_active"] is True
    r = client.put("/api/schedule", json={"enabled": False})
    assert r.json()["job_active"] is False


def test_scan_job_runs_scan(client):
    ingest(client, AWS, "aws")
    client.app.state.scan_job()
    scans = client.get("/api/scans").json()
    assert len(scans) == 1 and scans[0]["finding_count"] == 20


# --- auth ---

@pytest.fixture()
def authed_client(tmp_path):
    app = create_app(db_path=str(tmp_path / "auth.db"),
                     viewer_key="view-123", operator_key="op-456")
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_auth_missing_key_401(authed_client):
    assert authed_client.get("/api/summary").status_code == 401
    assert authed_client.post("/api/analyze").status_code == 401


def test_auth_wrong_key_403(authed_client):
    r = authed_client.get("/api/summary", headers={"X-API-Key": "wrong"})
    assert r.status_code == 403


def test_auth_viewer_reads_but_cannot_mutate(authed_client):
    v = {"X-API-Key": "view-123"}
    assert authed_client.get("/api/summary", headers=v).status_code == 200
    assert authed_client.post("/api/analyze", headers=v).status_code == 403
    assert authed_client.put("/api/policies", json={}, headers=v).status_code == 403


def test_auth_operator_full_access_and_audited_actor(authed_client):
    op = {"X-API-Key": "op-456"}
    assert ingest(authed_client, AWS, "aws", headers=op).status_code == 200
    assert authed_client.post("/api/analyze", headers=op).status_code == 200
    fid = authed_client.get("/api/findings", headers=op).json()[0]["id"]
    r = authed_client.post(f"/api/findings/{fid}/execute", json={"dry_run": True},
                           headers=op)
    assert r.status_code == 200
    assert r.json()["actor"] == "operator"


def test_auth_health_and_dashboard_stay_open(authed_client):
    assert authed_client.get("/health").status_code == 200
    assert authed_client.get("/").status_code == 200
