from datetime import date

import pytest

from app.adapters import db
from app.core.models import FindingResult, NormalizedResource


@pytest.fixture()
def session(tmp_path):
    engine = db.init_db(str(tmp_path / "test.db"))
    with db.session_scope(engine) as s:
        yield s


def res(**overrides):
    base = dict(
        provider="aws", resource_id="vol-1", resource_type="disk", region="us-east-1",
        billing_period="2026-06", monthly_cost=40.0, usage_hours=720.0,
        state="available", created_at=date(2026, 6, 1), tags={"Name": "x"},
    )
    base.update(overrides)
    return NormalizedResource(**base)


def fr(resource, rule="unattached_disk", savings=None):
    return FindingResult(resource=resource, rule=rule, category="storage",
                         severity="medium",
                         est_monthly_savings=savings if savings is not None else resource.monthly_cost,
                         reason="test reason")


def test_record_file_detects_duplicates(session):
    f1, created1 = db.record_file(session, "aws", "a.csv", "hash1")
    f2, created2 = db.record_file(session, "aws", "a.csv", "hash1")
    assert created1 is True and created2 is False
    assert f1.id == f2.id


def test_upsert_resources_idempotent(session):
    n1 = db.upsert_resources(session, [res()])
    n2 = db.upsert_resources(session, [res(monthly_cost=55.0)])
    assert n1 == 1 and n2 == 1
    rows = db.list_resources(session)
    assert len(rows) == 1
    assert rows[0].monthly_cost == 55.0


def test_apply_findings_inserts_open(session):
    db.upsert_resources(session, [res()])
    scan = db.create_scan(session, resource_count=1)
    stats = db.apply_findings(session, scan, [fr(res())])
    assert stats == {"new": 1, "updated": 0, "stale": 0}
    findings = db.list_findings(session)
    assert findings[0].status == "open"


def test_rescan_updates_not_duplicates(session):
    db.upsert_resources(session, [res()])
    scan1 = db.create_scan(session, resource_count=1)
    db.apply_findings(session, scan1, [fr(res())])
    scan2 = db.create_scan(session, resource_count=1)
    stats = db.apply_findings(session, scan2, [fr(res(monthly_cost=60.0), savings=60.0)])
    assert stats == {"new": 0, "updated": 1, "stale": 0}
    findings = db.list_findings(session)
    assert len(findings) == 1
    assert findings[0].est_monthly_savings == 60.0


def test_dismissed_survives_rescan(session):
    db.upsert_resources(session, [res()])
    scan1 = db.create_scan(session, resource_count=1)
    db.apply_findings(session, scan1, [fr(res())])
    f = db.list_findings(session)[0]
    db.set_finding_status(session, f.id, "dismissed")
    scan2 = db.create_scan(session, resource_count=1)
    db.apply_findings(session, scan2, [fr(res())])
    assert db.list_findings(session)[0].status == "dismissed"


def test_missing_finding_marked_stale(session):
    db.upsert_resources(session, [res()])
    scan1 = db.create_scan(session, resource_count=1)
    db.apply_findings(session, scan1, [fr(res())])
    scan2 = db.create_scan(session, resource_count=1)
    stats = db.apply_findings(session, scan2, [])  # resource fixed → finding gone
    assert stats["stale"] == 1
    assert db.list_findings(session)[0].status == "stale"


def test_set_status_unknown_id_raises(session):
    with pytest.raises(KeyError):
        db.set_finding_status(session, 999, "dismissed")


def test_list_findings_filters(session):
    db.upsert_resources(session, [res(), res(resource_id="eip-1", resource_type="ip",
                                             state="unassociated", monthly_cost=3.6)])
    scan = db.create_scan(session, resource_count=2)
    db.apply_findings(session, scan, [
        fr(res()),
        fr(res(resource_id="eip-1", resource_type="ip", monthly_cost=3.6), rule="orphaned_ip"),
    ])
    assert len(db.list_findings(session, rule="orphaned_ip")) == 1
    assert len(db.list_findings(session, min_savings=10.0)) == 1
    assert len(db.list_findings(session, provider="azure")) == 0
