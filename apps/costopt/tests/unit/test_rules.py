from datetime import date

from apps.costopt.core import engine  # noqa: F401  (imports register all rules)
from apps.costopt.core.models import NormalizedResource
from apps.costopt.core.rules.idle_vms import evaluate_idle_vms
from apps.costopt.core.rules.old_snapshots import evaluate_old_snapshots
from apps.costopt.core.rules.orphaned_ips import evaluate_orphaned_ips
from apps.costopt.core.rules.unattached_disks import evaluate_unattached_disks

TODAY = date(2026, 7, 18)


def res(**overrides):
    base = dict(
        provider="aws", resource_id="r-1", resource_type="other", region="us-east-1",
        billing_period="2026-06", monthly_cost=40.0, usage_hours=720.0,
        state="unknown", created_at=date(2026, 6, 1), tags={},
    )
    base.update(overrides)
    return NormalizedResource(**base)


# --- unattached disks ---

def test_unattached_disk_flagged():
    findings = evaluate_unattached_disks([res(resource_type="disk", state="available")])
    assert len(findings) == 1
    assert findings[0].rule == "unattached_disk"
    assert findings[0].est_monthly_savings == 40.0

def test_azure_unattached_state_flagged():
    findings = evaluate_unattached_disks([res(resource_type="disk", state="unattached")])
    assert len(findings) == 1

def test_attached_disk_not_flagged():
    assert evaluate_unattached_disks([res(resource_type="disk", state="attached")]) == []

def test_unknown_state_disk_skipped():
    assert evaluate_unattached_disks([res(resource_type="disk", state="unknown")]) == []


# --- idle VMs ---

def test_stopped_vm_with_cost_flagged():
    findings = evaluate_idle_vms([res(resource_type="vm", state="stopped", monthly_cost=62.4)])
    assert len(findings) == 1
    assert findings[0].severity == "high"

def test_low_cpu_running_vm_flagged():
    findings = evaluate_idle_vms([res(resource_type="vm", state="running",
                                      tags={"avgCpuPct": 0.4}, usage_hours=720)])
    assert len(findings) == 1

def test_busy_vm_not_flagged():
    assert evaluate_idle_vms([res(resource_type="vm", state="running", tags={"avgCpuPct": 55.0})]) == []

def test_unknown_state_vm_without_cpu_skipped():
    assert evaluate_idle_vms([res(resource_type="vm", state="unknown", tags={})]) == []

def test_stopped_vm_zero_cost_not_flagged():
    assert evaluate_idle_vms([res(resource_type="vm", state="stopped", monthly_cost=0.0)]) == []


# --- orphaned IPs ---

def test_unassociated_ip_flagged():
    findings = evaluate_orphaned_ips([res(resource_type="ip", state="unassociated", monthly_cost=3.6)])
    assert len(findings) == 1
    assert findings[0].severity == "low"

def test_associated_ip_not_flagged():
    assert evaluate_orphaned_ips([res(resource_type="ip", state="associated")]) == []


# --- old snapshots ---

def test_old_snapshot_flagged():
    findings = evaluate_old_snapshots([res(resource_type="snapshot", created_at=date(2025, 11, 2))],
                                      today=TODAY)
    assert len(findings) == 1
    assert "old" in findings[0].reason.lower() or "day" in findings[0].reason.lower()

def test_recent_snapshot_not_flagged():
    assert evaluate_old_snapshots([res(resource_type="snapshot", created_at=date(2026, 6, 1))],
                                  today=TODAY) == []

def test_snapshot_without_date_skipped():
    assert evaluate_old_snapshots([res(resource_type="snapshot", created_at=None)], today=TODAY) == []

def test_non_snapshot_ignored():
    assert evaluate_old_snapshots([res(resource_type="disk", created_at=date(2020, 1, 1))],
                                  today=TODAY) == []
