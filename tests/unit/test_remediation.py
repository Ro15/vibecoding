from datetime import date

from app.core.models import FindingResult, NormalizedResource
from app.core.remediation import build_plan, render_script

AZ_DISK = ("/subscriptions/aaaa/resourceGroups/rg-app/providers/"
           "Microsoft.Compute/disks/orphan-disk-0")


def finding(provider="aws", resource_id="vol-0abc", rtype="disk", rule="unattached_disk",
            savings=43.8):
    r = NormalizedResource(
        provider=provider, resource_id=resource_id, resource_type=rtype,
        region="us-east-1", billing_period="2026-06", monthly_cost=savings,
        usage_hours=720, state="available", created_at=date(2026, 1, 1), tags={},
    )
    return FindingResult(resource=r, rule=rule, category="storage", severity="medium",
                         est_monthly_savings=savings, reason="test")


def test_aws_disk_plan():
    plan = build_plan(finding())
    clis = [s.cli for s in plan.steps]
    assert any("describe-volumes" in c and "vol-0abc" in c for c in clis)
    assert any("delete-volume" in c and "vol-0abc" in c for c in clis)
    verify, delete = plan.steps[0], plan.steps[-1]
    assert verify.destructive is False and delete.destructive is True
    assert "boto3" in delete.sdk_code


def test_aws_vm_ip_snapshot_plans():
    vm = build_plan(finding(resource_id="i-0dead", rtype="vm", rule="idle_vm"))
    assert any("terminate-instances" in s.cli for s in vm.steps)
    ip = build_plan(finding(resource_id="eipalloc-9f8e", rtype="ip", rule="orphaned_ip"))
    assert any("release-address" in s.cli for s in ip.steps)
    snap = build_plan(finding(resource_id="snap-0old", rtype="snapshot", rule="old_snapshot"))
    assert any("delete-snapshot" in s.cli for s in snap.steps)


def test_azure_disk_plan_extracts_group_and_name():
    plan = build_plan(finding(provider="azure", resource_id=AZ_DISK))
    clis = " ".join(s.cli for s in plan.steps)
    assert "az disk delete" in clis
    assert "--resource-group rg-app" in clis
    assert "--name orphan-disk-0" in clis
    assert any("azure" in s.sdk_code.lower() or "ComputeManagementClient" in s.sdk_code
               for s in plan.steps if s.destructive)


def test_azure_vm_ip_snapshot_plans():
    vm = build_plan(finding(provider="azure", rtype="vm", rule="idle_vm",
                            resource_id=AZ_DISK.replace("disks/orphan-disk-0", "virtualMachines/idle-vm-0")))
    assert any("az vm delete" in s.cli for s in vm.steps)
    ip = build_plan(finding(provider="azure", rtype="ip", rule="orphaned_ip",
                            resource_id=AZ_DISK.replace("Microsoft.Compute/disks/orphan-disk-0",
                                                        "Microsoft.Network/publicIPAddresses/orphan-ip-0")))
    assert any("az network public-ip delete" in s.cli for s in ip.steps)
    snap = build_plan(finding(provider="azure", rtype="snapshot", rule="old_snapshot",
                              resource_id=AZ_DISK.replace("disks/orphan-disk-0", "snapshots/old-snap-0")))
    assert any("az snapshot delete" in s.cli for s in snap.steps)


def test_every_plan_has_verify_before_destroy():
    for f in [finding(), finding(rtype="vm", rule="idle_vm", resource_id="i-1"),
              finding(rtype="ip", rule="orphaned_ip", resource_id="eipalloc-1"),
              finding(rtype="snapshot", rule="old_snapshot", resource_id="snap-1")]:
        plan = build_plan(f)
        orders = [(s.order, s.destructive) for s in plan.steps]
        assert orders == sorted(orders, key=lambda x: x[0])
        first_destructive = next(i for i, s in enumerate(plan.steps) if s.destructive)
        assert first_destructive > 0  # at least one verify step first


def test_render_script_bundles_findings():
    findings = [(1, finding()), (2, finding(resource_id="eipalloc-9f8e", rtype="ip",
                                            rule="orphaned_ip", savings=3.6))]
    script = render_script(findings, provider="aws")
    assert script.startswith("#!/usr/bin/env bash")
    assert "Finding #1" in script and "Finding #2" in script
    assert "delete-volume" in script and "release-address" in script
    assert script.index("describe-volumes") < script.index("delete-volume")
    assert "$43.80/mo" in script
