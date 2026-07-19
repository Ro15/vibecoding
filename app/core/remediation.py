"""Remediation generator: turns findings into verify + decommission commands.

Plans are structured data (RemStep) so they can be rendered as CLI text,
SDK snippets, or a reviewable shell script. Nothing here executes anything.
"""
from __future__ import annotations

import re

from app.core.models import FindingResult, RemediationPlan, RemStep


def _azure_parts(resource_id: str) -> tuple[str, str]:
    """Extract (resource_group, name) from an Azure resource ID path."""
    m = re.search(r"/resourceGroups/([^/]+)/", resource_id, re.IGNORECASE)
    group = m.group(1) if m else "<resource-group>"
    name = resource_id.rstrip("/").rsplit("/", 1)[-1] or "<name>"
    return group, name


def _steps_aws(rtype: str, rid: str) -> list[RemStep]:
    if rtype == "disk":
        return [
            RemStep(1, "Verify the volume is unattached (State should be 'available')",
                    f"aws ec2 describe-volumes --volume-ids {rid} "
                    f"--query 'Volumes[0].State'",
                    f"import boto3\nec2 = boto3.client('ec2')\n"
                    f"state = ec2.describe_volumes(VolumeIds=['{rid}'])['Volumes'][0]['State']\n"
                    f"assert state == 'available', f'not orphaned: {{state}}'", False),
            RemStep(2, "(Optional) snapshot before deletion for rollback",
                    f"aws ec2 create-snapshot --volume-id {rid} "
                    f"--description 'pre-decommission backup'",
                    f"ec2.create_snapshot(VolumeId='{rid}', "
                    f"Description='pre-decommission backup')", False),
            RemStep(3, "Delete the unattached volume",
                    f"aws ec2 delete-volume --volume-id {rid}",
                    f"import boto3\nboto3.client('ec2').delete_volume(VolumeId='{rid}')", True),
        ]
    if rtype == "vm":
        return [
            RemStep(1, "Verify instance state and recent activity",
                    f"aws ec2 describe-instances --instance-ids {rid} "
                    f"--query 'Reservations[0].Instances[0].State.Name'",
                    f"import boto3\nec2 = boto3.client('ec2')\n"
                    f"state = ec2.describe_instances(InstanceIds=['{rid}'])"
                    f"['Reservations'][0]['Instances'][0]['State']['Name']\nprint(state)", False),
            RemStep(2, "Terminate the idle instance",
                    f"aws ec2 terminate-instances --instance-ids {rid}",
                    f"import boto3\nboto3.client('ec2').terminate_instances(InstanceIds=['{rid}'])", True),
        ]
    if rtype == "ip":
        return [
            RemStep(1, "Verify the Elastic IP has no association",
                    f"aws ec2 describe-addresses --allocation-ids {rid} "
                    f"--query 'Addresses[0].AssociationId'",
                    f"import boto3\naddr = boto3.client('ec2').describe_addresses("
                    f"AllocationIds=['{rid}'])['Addresses'][0]\n"
                    f"assert 'AssociationId' not in addr, 'still associated'", False),
            RemStep(2, "Release the unassociated Elastic IP",
                    f"aws ec2 release-address --allocation-id {rid}",
                    f"import boto3\nboto3.client('ec2').release_address(AllocationId='{rid}')", True),
        ]
    if rtype == "snapshot":
        return [
            RemStep(1, "Verify snapshot age and that no AMI depends on it",
                    f"aws ec2 describe-snapshots --snapshot-ids {rid} "
                    f"--query 'Snapshots[0].StartTime'",
                    f"import boto3\nsnap = boto3.client('ec2').describe_snapshots("
                    f"SnapshotIds=['{rid}'])['Snapshots'][0]\nprint(snap['StartTime'])", False),
            RemStep(2, "Delete the aged snapshot",
                    f"aws ec2 delete-snapshot --snapshot-id {rid}",
                    f"import boto3\nboto3.client('ec2').delete_snapshot(SnapshotId='{rid}')", True),
        ]
    return [RemStep(1, "Manual review required (unrecognized resource type)",
                    f"aws resourcegroupstaggingapi get-resources --resource-arn-list {rid}",
                    "# manual review", False)]


def _steps_azure(rtype: str, rid: str) -> list[RemStep]:
    group, name = _azure_parts(rid)
    sdk_prefix = ("from azure.identity import DefaultAzureCredential\n"
                  "from azure.mgmt.compute import ComputeManagementClient\n"
                  "client = ComputeManagementClient(DefaultAzureCredential(), subscription_id)\n")
    if rtype == "disk":
        return [
            RemStep(1, "Verify the disk is unattached (diskState should be 'Unattached')",
                    f"az disk show --resource-group {group} --name {name} --query diskState",
                    sdk_prefix + f"disk = client.disks.get('{group}', '{name}')\n"
                                 f"assert disk.disk_state == 'Unattached'", False),
            RemStep(2, "Delete the unattached managed disk",
                    f"az disk delete --resource-group {group} --name {name} --yes",
                    sdk_prefix + f"client.disks.begin_delete('{group}', '{name}').result()", True),
        ]
    if rtype == "vm":
        return [
            RemStep(1, "Verify the VM power state",
                    f"az vm get-instance-view --resource-group {group} --name {name} "
                    f"--query instanceView.statuses[1].displayStatus",
                    sdk_prefix + f"view = client.virtual_machines.instance_view('{group}', '{name}')\n"
                                 f"print([s.display_status for s in view.statuses])", False),
            RemStep(2, "Delete the idle VM",
                    f"az vm delete --resource-group {group} --name {name} --yes",
                    sdk_prefix + f"client.virtual_machines.begin_delete('{group}', '{name}').result()", True),
        ]
    if rtype == "ip":
        net_sdk = ("from azure.identity import DefaultAzureCredential\n"
                   "from azure.mgmt.network import NetworkManagementClient\n"
                   "net = NetworkManagementClient(DefaultAzureCredential(), subscription_id)\n")
        return [
            RemStep(1, "Verify the public IP has no ipConfiguration (unassociated)",
                    f"az network public-ip show --resource-group {group} --name {name} "
                    f"--query ipConfiguration",
                    net_sdk + f"ip = net.public_ip_addresses.get('{group}', '{name}')\n"
                              f"assert ip.ip_configuration is None, 'still associated'", False),
            RemStep(2, "Delete the unassociated public IP",
                    f"az network public-ip delete --resource-group {group} --name {name}",
                    net_sdk + f"net.public_ip_addresses.begin_delete('{group}', '{name}').result()", True),
        ]
    if rtype == "snapshot":
        return [
            RemStep(1, "Verify snapshot creation time",
                    f"az snapshot show --resource-group {group} --name {name} --query timeCreated",
                    sdk_prefix + f"snap = client.snapshots.get('{group}', '{name}')\n"
                                 f"print(snap.time_created)", False),
            RemStep(2, "Delete the aged snapshot",
                    f"az snapshot delete --resource-group {group} --name {name}",
                    sdk_prefix + f"client.snapshots.begin_delete('{group}', '{name}').result()", True),
        ]
    return [RemStep(1, "Manual review required (unrecognized resource type)",
                    f"az resource show --ids {rid}", "# manual review", False)]


def build_plan(finding: FindingResult) -> RemediationPlan:
    r = finding.resource
    steps = _steps_aws(r.resource_type, r.resource_id) if r.provider == "aws" \
        else _steps_azure(r.resource_type, r.resource_id)
    return RemediationPlan(rule=finding.rule, provider=r.provider,
                           resource_id=r.resource_id, steps=steps)


def render_script(findings_with_ids: list[tuple[int, FindingResult]], provider: str) -> str:
    """Render a reviewable bash script for open findings of one provider."""
    lines = [
        "#!/usr/bin/env bash",
        f"# CostOpt remediation script — provider: {provider}",
        "# REVIEW EVERY LINE BEFORE RUNNING. Verify commands come before destructive ones.",
        "set -euo pipefail",
        "",
    ]
    total = 0.0
    for fid, f in findings_with_ids:
        if f.resource.provider != provider:
            continue
        total += f.est_monthly_savings
        lines.append(f"# Finding #{fid}: {f.rule} — {f.resource.resource_id} "
                     f"(${f.est_monthly_savings:.2f}/mo)")
        plan = build_plan(f)
        for step in plan.steps:
            marker = "" if step.destructive else "   # verify"
            lines.append(f"{step.cli}{marker}")
        lines.append("")
    lines.insert(4, f"# Total estimated savings: ${total:.2f}/mo")
    return "\n".join(lines)
