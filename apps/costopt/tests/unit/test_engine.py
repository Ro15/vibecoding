from datetime import date

from apps.costopt.core.engine import run_rules
from apps.costopt.core.models import NormalizedResource

TODAY = date(2026, 7, 18)


def res(**overrides):
    base = dict(
        provider="aws", resource_id="r-1", resource_type="other", region="us-east-1",
        billing_period="2026-06", monthly_cost=40.0, usage_hours=720.0,
        state="unknown", created_at=date(2026, 6, 1), tags={"owner": "team-x"},
    )
    base.update(overrides)
    return NormalizedResource(**base)


def test_engine_combines_all_rules():
    resources = [
        res(resource_id="vol-1", resource_type="disk", state="available"),
        res(resource_id="i-1", resource_type="vm", state="stopped", monthly_cost=60.0),
        res(resource_id="eip-1", resource_type="ip", state="unassociated", monthly_cost=3.6),
        res(resource_id="snap-1", resource_type="snapshot", created_at=date(2025, 1, 1)),
        res(resource_id="vol-ok", resource_type="disk", state="attached"),
    ]
    findings = run_rules(resources, today=TODAY)
    rules_hit = {f.rule for f in findings}
    assert rules_hit == {"unattached_disk", "idle_vm", "orphaned_ip", "old_snapshot"}
    assert len(findings) == 4


def test_engine_severity_assigned():
    findings = run_rules([res(resource_id="vol-1", resource_type="disk",
                              state="available", monthly_cost=87.5)], today=TODAY)
    assert findings[0].severity == "high"


def test_engine_empty_input():
    assert run_rules([], today=TODAY) == []
