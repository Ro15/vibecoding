"""Unit tests for the v1.1 feature set."""
import json
from datetime import date
from pathlib import Path

import pytest

from app.adapters import db
from app.core import engine as _engine  # noqa: F401  (registers rules)
from app.core.execution import SimulatedExecutor
from app.core.models import FindingResult, NormalizedResource
from app.core.policies import DEFAULTS, merge_policies, severity_for
from app.core.providers.focus import parse_focus
from app.core.providers.gcp import parse_gcp
from app.core.remediation import build_plan
from app.core.rules.aged_stopped_vms import evaluate_aged_stopped_vms
from app.core.rules.idle_load_balancers import evaluate_idle_load_balancers
from app.core.rules.idle_vms import evaluate_idle_vms
from app.core.rules.oversized_vms import evaluate_oversized_vms
from app.core.rules.untagged_resources import evaluate_untagged_resources
from app.core.rules.unused_nat_gateways import evaluate_unused_nat_gateways

ROOT = Path(__file__).parents[2]
TODAY = date(2026, 7, 18)


def res(**overrides):
    base = dict(
        provider="aws", resource_id="r-1", resource_type="other", region="us-east-1",
        billing_period="2026-06", monthly_cost=40.0, usage_hours=720.0,
        state="unknown", created_at=date(2026, 6, 1), tags={"owner": "team-x"},
    )
    base.update(overrides)
    return NormalizedResource(**base)


# --- policies ---

def test_merge_policies_casts_types():
    merged = merge_policies({"snapshot_retention_days": "120",
                             "cpu_idle_threshold_pct": "5.5",
                             "webhook_url": "http://x"})
    assert merged["snapshot_retention_days"] == 120
    assert merged["cpu_idle_threshold_pct"] == 5.5
    assert merged["webhook_url"] == "http://x"


def test_merge_policies_ignores_unknown_and_bad():
    merged = merge_policies({"nope": "1", "snapshot_retention_days": "abc"})
    assert "nope" not in merged
    assert merged["snapshot_retention_days"] == DEFAULTS["snapshot_retention_days"]


def test_severity_respects_policy_bands():
    p = merge_policies({"severity_high_usd": "100", "severity_medium_usd": "20"})
    assert severity_for(99.0, p) == "medium"
    assert severity_for(100.0, p) == "high"
    assert severity_for(19.0, p) == "low"


# --- new rules ---

def test_oversized_vm_flagged_with_half_savings():
    f = evaluate_oversized_vms([res(resource_type="vm", state="running",
                                    monthly_cost=140.0, tags={"avgCpuPct": 22.5, "owner": "t"})])
    assert len(f) == 1
    assert f[0].est_monthly_savings == 70.0


def test_oversized_vm_not_flagged_when_busy_or_idle():
    assert evaluate_oversized_vms([res(resource_type="vm", state="running",
                                       tags={"avgCpuPct": 55.0})]) == []
    # below idle threshold → idle_vm's territory, not rightsizing
    assert evaluate_oversized_vms([res(resource_type="vm", state="running",
                                       tags={"avgCpuPct": 1.0})]) == []


def test_idle_lb_flagged_and_metricless_skipped():
    hit = evaluate_idle_load_balancers([res(resource_type="lb", monthly_cost=16.2,
                                            tags={"requestCount": 12.0})])
    assert len(hit) == 1
    assert evaluate_idle_load_balancers([res(resource_type="lb", tags={})]) == []


def test_unused_natgw_flagged():
    hit = evaluate_unused_nat_gateways([res(resource_type="natgw", monthly_cost=32.85,
                                            tags={"dataProcessedGB": 0.2})])
    assert len(hit) == 1
    assert evaluate_unused_nat_gateways([res(resource_type="natgw",
                                             tags={"dataProcessedGB": 500.0})]) == []


def test_aged_stopped_vm_and_idle_vm_do_not_overlap():
    aged = res(resource_type="vm", state="stopped", monthly_cost=21.5,
               tags={"stoppedDate": "2026-04-05", "owner": "t"})
    recent = res(resource_id="r-2", resource_type="vm", state="stopped", monthly_cost=15.0,
                 tags={"owner": "t"})
    aged_hits = evaluate_aged_stopped_vms([aged, recent], today=TODAY)
    idle_hits = evaluate_idle_vms([aged, recent], today=TODAY)
    assert [f.resource.resource_id for f in aged_hits] == ["r-1"]
    assert [f.resource.resource_id for f in idle_hits] == ["r-2"]


def test_untagged_rule_flags_only_unowned_above_floor():
    unowned = res(resource_id="u1", monthly_cost=28.4, tags={})
    cheap_unowned = res(resource_id="u2", monthly_cost=2.0, tags={})
    owned = res(resource_id="o1", monthly_cost=95.0)
    hits = evaluate_untagged_resources([unowned, cheap_unowned, owned])
    assert [f.resource.resource_id for f in hits] == ["u1"]
    assert hits[0].est_monthly_savings == 0.0
    assert hits[0].category == "governance"


# --- GCP parser ---

def test_gcp_parser_sample_file():
    data = (ROOT / "sample_data" / "gcp_billing.json").read_bytes()
    resources, errors = parse_gcp(data)
    assert errors == []
    assert len(resources) == 12
    by_name = {r.resource_id.rsplit("/", 1)[-1]: r for r in resources}
    assert by_name["orphan-disk-0"].resource_type == "disk"
    assert by_name["orphan-disk-0"].state == "unattached"
    assert by_name["idle-vm-0"].state == "stopped"
    assert by_name["old-snap-0"].created_at == date(2025, 11, 2)
    assert by_name["oversized-vm-0"].tags["avgCpuPct"] == 25.0
    assert by_name["mystery-vm-0"].tags.get("owner") is None


def test_gcp_parser_bad_rows():
    items = [{"resource": {"name": ""}, "cost": 1},
             {"resource": {"name": "x/disks/d"}, "cost": "bad"}]
    resources, errors = parse_gcp(json.dumps(items).encode())
    assert resources == [] and len(errors) == 2
    with pytest.raises(ValueError):
        parse_gcp(b"{not a list}")


# --- FOCUS parser ---

def test_focus_parser_sample_maps_providers():
    data = (ROOT / "sample_data" / "focus_costs.csv").read_bytes()
    resources, errors = parse_focus(data)
    assert errors == []
    assert len(resources) == 6
    providers = {r.resource_id: r.provider for r in resources}
    assert providers["vol-focus0001"] == "aws"
    assert any(p == "azure" for p in providers.values())
    assert any(p == "gcp" for p in providers.values())
    vol = next(r for r in resources if r.resource_id == "vol-focus0001")
    assert vol.resource_type == "disk" and vol.state == "unattached"


def test_focus_parser_unknown_provider_is_row_error():
    rows = [{"ProviderName": "OracleCloud", "ResourceId": "x", "ResourceType": "Disk",
             "BilledCost": 1, "ConsumedQuantity": 1, "Tags": "{}"}]
    resources, errors = parse_focus(json.dumps(rows).encode())
    assert resources == [] and len(errors) == 1


# --- remediation for new rules/providers ---

def fr(provider, rid, rtype, rule):
    return FindingResult(resource=res(provider=provider, resource_id=rid,
                                      resource_type=rtype),
                         rule=rule, category="x", severity="low",
                         est_monthly_savings=10.0, reason="t")


def test_gcp_remediation_commands():
    plan = build_plan(fr("gcp", "projects/p/zones/us-central1-a/disks/orphan-disk-0",
                         "disk", "unattached_disk"))
    clis = " ".join(s.cli for s in plan.steps)
    assert "gcloud compute disks delete orphan-disk-0 --zone=us-central1-a" in clis


def test_lb_natgw_remediation():
    lb = build_plan(fr("aws", "lb-0idle0000", "lb", "idle_load_balancer"))
    assert any("delete-load-balancer" in s.cli for s in lb.steps)
    nat = build_plan(fr("azure",
                        "/subscriptions/s/resourceGroups/rg-net/providers/Microsoft.Network/natGateways/unused-nat-0",
                        "natgw", "unused_nat_gateway"))
    assert any("az network nat gateway delete" in s.cli for s in nat.steps)


def test_oversized_plan_is_resize_not_delete():
    plan = build_plan(fr("aws", "i-0oversz0000", "vm", "oversized_vm"))
    clis = " ".join(s.cli for s in plan.steps)
    assert "modify-instance-attribute" in clis
    assert "terminate-instances" not in clis


def test_untagged_plan_is_tagging_and_nondestructive():
    plan = build_plan(fr("aws", "vol-0untag0000", "disk", "untagged_resource"))
    assert all(not s.destructive for s in plan.steps)
    assert "create-tags" in plan.steps[0].cli


# --- simulated executor ---

def test_simulated_executor_never_hides_destructive_steps():
    plan = build_plan(fr("aws", "vol-1", "disk", "unattached_disk"))
    result = SimulatedExecutor().execute(plan, dry_run=True)
    assert result.succeeded and result.dry_run
    assert "DESTRUCTIVE" in result.output
    assert all(cmd in result.output for cmd in result.commands)


# --- realization stamping ---

def test_remediated_status_stamps_realization(tmp_path):
    engine = db.init_db(str(tmp_path / "t.db"))
    with db.session_scope(engine) as s:
        scan = db.create_scan(s, resource_count=1)
        db.apply_findings(s, scan, [FindingResult(
            resource=res(resource_id="vol-9", resource_type="disk", state="available"),
            rule="unattached_disk", category="storage", severity="medium",
            est_monthly_savings=43.8, reason="t")])
        f = db.list_findings(s)[0]
        assert f.owner == "team-x"
        row = db.set_finding_status(s, f.id, "remediated")
        assert row.remediated_at is not None
        assert row.realized_monthly_savings == 43.8


def test_policies_roundtrip(tmp_path):
    engine = db.init_db(str(tmp_path / "p.db"))
    with db.session_scope(engine) as s:
        assert db.get_policies(s)["snapshot_retention_days"] == 90
        db.set_policies(s, {"snapshot_retention_days": 120})
        assert db.get_policies(s)["snapshot_retention_days"] == 120
        with pytest.raises(ValueError):
            db.set_policies(s, {"bogus_key": 1})
