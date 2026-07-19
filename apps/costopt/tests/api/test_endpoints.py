"""Per-endpoint E2E tests against the full app with a temp DB."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.costopt.api.main import create_app

ROOT = Path(__file__).parents[2]
AWS_SAMPLE = ROOT / "sample_data" / "aws_cur.csv"
AZURE_SAMPLE = ROOT / "sample_data" / "azure_costs.json"


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "api.db"))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def ingest(client, path: Path, provider: str):
    with open(path, "rb") as f:
        return client.post("/api/ingest", files={"file": (path.name, f)},
                           data={"provider": provider})


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_ingest_aws_ok(client):
    r = ingest(client, AWS_SAMPLE, "aws")
    assert r.status_code == 200
    body = r.json()
    assert body["duplicate"] is False
    assert body["rows_ok"] == 64 and body["rows_failed"] == 0
    assert body["resources_upserted"] == 64


def test_ingest_duplicate_noop(client):
    ingest(client, AWS_SAMPLE, "aws")
    r = ingest(client, AWS_SAMPLE, "aws")
    assert r.json()["duplicate"] is True
    assert r.json()["resources_upserted"] == 0


def test_ingest_unknown_provider_422(client):
    r = ingest(client, AWS_SAMPLE, "oracle")
    assert r.status_code == 422


def test_ingest_garbage_422(client):
    r = client.post("/api/ingest", files={"file": ("x.csv", b"\xff\xfe\x00garbage")},
                    data={"provider": "aws"})
    assert r.status_code == 422
    r2 = client.post("/api/ingest", files={"file": ("x.csv", b"colA,colB\n1,2")},
                     data={"provider": "aws"})
    assert r2.status_code == 422


def test_analyze_finds_seeded_waste(client):
    ingest(client, AWS_SAMPLE, "aws")
    ingest(client, AZURE_SAMPLE, "azure")
    r = client.post("/api/analyze")
    assert r.status_code == 200
    body = r.json()
    # seeded: aws 20, azure 14
    assert body["findings_new"] == 34
    assert body["open_findings"] == 34
    assert body["total_est_monthly_savings"] > 400


def test_reanalyze_does_not_duplicate(client):
    ingest(client, AWS_SAMPLE, "aws")
    client.post("/api/analyze")
    r = client.post("/api/analyze")
    body = r.json()
    assert body["findings_new"] == 0
    assert body["findings_updated"] == 20
    assert body["open_findings"] == 20


def test_findings_filters(client):
    ingest(client, AWS_SAMPLE, "aws")
    ingest(client, AZURE_SAMPLE, "azure")
    client.post("/api/analyze")
    all_f = client.get("/api/findings").json()
    assert len(all_f) == 34
    aws_only = client.get("/api/findings", params={"provider": "aws"}).json()
    assert len(aws_only) == 20 and all(f["provider"] == "aws" for f in aws_only)
    ip_only = client.get("/api/findings", params={"rule": "orphaned_ip"}).json()
    assert len(ip_only) == 5
    big = client.get("/api/findings", params={"min_savings": 50}).json()
    assert all(f["est_monthly_savings"] >= 50 for f in big)
    # savings sorted desc
    savings = [f["est_monthly_savings"] for f in all_f]
    assert savings == sorted(savings, reverse=True)


def test_patch_finding_lifecycle(client):
    ingest(client, AWS_SAMPLE, "aws")
    client.post("/api/analyze")
    fid = client.get("/api/findings").json()[0]["id"]
    r = client.patch(f"/api/findings/{fid}", json={"status": "dismissed"})
    assert r.status_code == 200 and r.json()["status"] == "dismissed"
    assert client.patch("/api/findings/99999", json={"status": "dismissed"}).status_code == 404
    assert client.patch(f"/api/findings/{fid}", json={"status": "bogus"}).status_code == 422


def test_remediation_plan(client):
    ingest(client, AWS_SAMPLE, "aws")
    client.post("/api/analyze")
    disk = next(f for f in client.get("/api/findings").json()
                if f["rule"] == "unattached_disk" and f["provider"] == "aws")
    r = client.get(f"/api/findings/{disk['id']}/remediation")
    assert r.status_code == 200
    plan = r.json()
    assert plan["resource_id"] == disk["resource_id"]
    clis = [s["cli"] for s in plan["steps"]]
    assert any("describe-volumes" in c for c in clis)
    assert any("delete-volume" in c for c in clis)
    destructives = [s["destructive"] for s in plan["steps"]]
    assert destructives[0] is False and destructives[-1] is True
    assert client.get("/api/findings/99999/remediation").status_code == 404


def test_remediation_script_download(client):
    ingest(client, AWS_SAMPLE, "aws")
    client.post("/api/analyze")
    r = client.get("/api/remediation/script", params={"provider": "aws"})
    assert r.status_code == 200
    assert "text/x-shellscript" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    assert r.text.startswith("#!/usr/bin/env bash")
    assert "delete-volume" in r.text and "release-address" in r.text
    assert client.get("/api/remediation/script", params={"provider": "oracle"}).status_code == 422


def test_summary_aggregates(client):
    ingest(client, AWS_SAMPLE, "aws")
    ingest(client, AZURE_SAMPLE, "azure")
    client.post("/api/analyze")
    s = client.get("/api/summary").json()
    assert s["open_findings"] == 34
    assert s["total_monthly_waste"] > 0
    assert s["potential_annual_savings"] == round(s["total_monthly_waste"] * 12, 2)
    assert set(s["by_provider"]) == {"aws", "azure"}
    assert set(s["by_category"]) == {"storage", "compute", "network", "governance"}
    assert len(s["top_offenders"]) == 5
    assert len(s["scan_trend"]) == 1


def test_scans_history(client):
    ingest(client, AWS_SAMPLE, "aws")
    client.post("/api/analyze")
    client.post("/api/analyze")
    scans = client.get("/api/scans").json()
    assert len(scans) == 2
    assert scans[0]["id"] < scans[1]["id"]


def test_dashboard_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_full_flow(client):
    assert ingest(client, AWS_SAMPLE, "aws").status_code == 200
    assert ingest(client, AZURE_SAMPLE, "azure").status_code == 200
    analyze = client.post("/api/analyze").json()
    assert analyze["open_findings"] == 34
    findings = client.get("/api/findings").json()
    plan = client.get(f"/api/findings/{findings[0]['id']}/remediation").json()
    assert plan["steps"]
    script = client.get("/api/remediation/script", params={"provider": "azure"}).text
    assert "az disk delete" in script
