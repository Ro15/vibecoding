from datetime import date

import pytest

from app.core import registry
from app.core.models import FindingResult, NormalizedResource


def make_resource(**overrides):
    base = dict(
        provider="aws",
        resource_id="vol-123",
        resource_type="disk",
        region="us-east-1",
        billing_period="2026-06",
        monthly_cost=40.0,
        usage_hours=720.0,
        state="available",
        created_at=date(2026, 1, 1),
        tags={},
        raw_ref=None,
    )
    base.update(overrides)
    return NormalizedResource(**base)


def test_provider_registration_and_lookup():
    @registry.provider("testcloud")
    def parse(file_bytes, billing_period=None):
        return [], []

    assert registry.get_provider("testcloud") is parse


def test_unknown_provider_raises():
    with pytest.raises(KeyError):
        registry.get_provider("nope")


def test_rule_registration_carries_category():
    @registry.rule("test_rule", category="storage")
    def evaluate(resources):
        return []

    entry = registry.all_rules()["test_rule"]
    assert entry.category == "storage"
    assert entry.evaluate is evaluate


def test_severity_thresholds():
    assert registry.severity_for(50.0) == "high"
    assert registry.severity_for(120.0) == "high"
    assert registry.severity_for(10.0) == "medium"
    assert registry.severity_for(49.99) == "medium"
    assert registry.severity_for(9.99) == "low"


def test_finding_result_holds_resource():
    r = make_resource()
    f = FindingResult(
        resource=r,
        rule="unattached_disk",
        category="storage",
        severity="medium",
        est_monthly_savings=40.0,
        reason="disk is unattached",
    )
    assert f.resource.resource_id == "vol-123"
