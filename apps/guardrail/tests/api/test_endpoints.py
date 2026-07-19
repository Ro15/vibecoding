"""Per-endpoint E2E tests for Guardrail."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.guardrail.api.main import create_app

SD = Path(__file__).parents[2] / "sample_data"


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "g.db"))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def ingest(client, name, fmt):
    with open(SD / name, "rb") as f:
        return client.post("/api/ingest", files={"file": (name, f)}, data={"format": fmt})


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_ingest_hcl_scores_risk(client):
    r = ingest(client, "insecure.tf", "hcl")
    assert r.status_code == 200
    b = r.json()
    assert b["resource_count"] == 7
    assert b["finding_count"] == 12
    assert b["risk_score"] == 100 and b["grade"] == "F"
    assert b["parse_errors"] == []


def test_ingest_cloudformation(client):
    b = ingest(client, "insecure_cfn.yaml", "cloudformation").json()
    assert b["source_format"] == "cloudformation"
    assert b["finding_count"] == 5
    assert b["grade"] == "F"


def test_ingest_tfplan(client):
    b = ingest(client, "plan.json", "tfplan").json()
    assert b["resource_count"] == 3
    assert b["finding_count"] == 4


def test_secure_file_is_clean(client):
    b = ingest(client, "secure.tf", "hcl").json()
    assert b["finding_count"] == 0
    assert b["risk_score"] == 0 and b["grade"] == "A+"


def test_ingest_unknown_format_422(client):
    with open(SD / "insecure.tf", "rb") as f:
        r = client.post("/api/ingest", files={"file": ("x.tf", f)}, data={"format": "puppet"})
    assert r.status_code == 422


def test_ingest_garbage_422(client):
    r = client.post("/api/ingest", files={"file": ("x.tf", b"resource {{{")},
                    data={"format": "hcl"})
    assert r.status_code == 422


def test_findings_filters(client):
    ingest(client, "insecure.tf", "hcl")
    all_f = client.get("/api/findings").json()
    assert len(all_f) == 12
    highs = client.get("/api/findings", params={"severity": "high"}).json()
    assert all(f["severity"] == "high" for f in highs) and len(highs) == 7
    s3 = client.get("/api/findings", params={"rtype": "s3_bucket"}).json()
    assert all(f["rtype"] == "s3_bucket" for f in s3)
    cis52 = client.get("/api/findings", params={"framework": "CIS 5.2"}).json()
    assert all(f["framework"] == "CIS 5.2" for f in cis52)
    # sorted critical-first
    sev = [f["severity"] for f in all_f]
    assert sev[0] == "critical"


def test_finding_detail_and_remediation(client):
    ingest(client, "insecure.tf", "hcl")
    fid = client.get("/api/findings").json()[0]["id"]
    r = client.get(f"/api/findings/{fid}")
    assert r.status_code == 200
    assert r.json()["remediation"]
    assert client.get("/api/findings/99999").status_code == 404


def test_summary_aggregates(client):
    ingest(client, "insecure.tf", "hcl")
    s = client.get("/api/summary").json()
    assert s["risk_score"] == 100 and s["grade"] == "F"
    assert s["by_severity"]["critical"] == 1
    assert "s3_bucket" in s["by_rtype"]
    assert "CIS 5.2" in s["by_framework"]
    assert len(s["scan_trend"]) == 1


def test_summary_empty(client):
    s = client.get("/api/summary").json()
    assert s["risk_score"] == 0 and s["finding_count"] == 0


def test_latest_scan_drives_findings(client):
    ingest(client, "insecure.tf", "hcl")
    ingest(client, "secure.tf", "hcl")  # newer scan is clean
    assert client.get("/api/findings").json() == []
    s = client.get("/api/summary").json()
    assert s["grade"] == "A+"


def test_scans_history(client):
    ingest(client, "insecure.tf", "hcl")
    ingest(client, "secure.tf", "hcl")
    scans = client.get("/api/scans").json()
    assert len(scans) == 2
    assert scans[0]["grade"] == "F" and scans[1]["grade"] == "A+"


def test_dashboard_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
