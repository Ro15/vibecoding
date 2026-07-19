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


def _gcp_parts(resource_id: str) -> tuple[str, str]:
    """Extract (zone_or_region_flag, name) from a GCP resource path."""
    name = resource_id.rstrip("/").rsplit("/", 1)[-1] or "<name>"
    m = re.search(r"/zones/([^/]+)/", resource_id)
    if m:
        return f"--zone={m.group(1)}", name
    m = re.search(r"/regions/([^/]+)/", resource_id)
    if m:
        return f"--region={m.group(1)}", name
    return "--zone=<zone>", name


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
    if rtype == "lb":
        return [
            RemStep(1, "Verify the load balancer has no meaningful traffic",
                    f"aws elbv2 describe-load-balancers --names {rid}",
                    f"import boto3\nelb = boto3.client('elbv2')\n"
                    f"print(elb.describe_load_balancers(Names=['{rid}']))", False),
            RemStep(2, "Delete the idle load balancer",
                    f"aws elbv2 delete-load-balancer --load-balancer-arn "
                    f"$(aws elbv2 describe-load-balancers --names {rid} "
                    f"--query 'LoadBalancers[0].LoadBalancerArn' --output text)",
                    f"import boto3\nelb = boto3.client('elbv2')\n"
                    f"arn = elb.describe_load_balancers(Names=['{rid}'])"
                    f"['LoadBalancers'][0]['LoadBalancerArn']\n"
                    f"elb.delete_load_balancer(LoadBalancerArn=arn)", True),
        ]
    if rtype == "natgw":
        return [
            RemStep(1, "Verify NAT gateway state and low utilization",
                    f"aws ec2 describe-nat-gateways --nat-gateway-ids {rid}",
                    f"import boto3\nprint(boto3.client('ec2').describe_nat_gateways("
                    f"NatGatewayIds=['{rid}']))", False),
            RemStep(2, "Delete the unused NAT gateway",
                    f"aws ec2 delete-nat-gateway --nat-gateway-id {rid}",
                    f"import boto3\nboto3.client('ec2').delete_nat_gateway("
                    f"NatGatewayId='{rid}')", True),
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
    if rtype == "lb":
        net_sdk = ("from azure.identity import DefaultAzureCredential\n"
                   "from azure.mgmt.network import NetworkManagementClient\n"
                   "net = NetworkManagementClient(DefaultAzureCredential(), subscription_id)\n")
        return [
            RemStep(1, "Verify the load balancer has no active backend traffic",
                    f"az network lb show --resource-group {group} --name {name}",
                    net_sdk + f"print(net.load_balancers.get('{group}', '{name}'))", False),
            RemStep(2, "Delete the idle load balancer",
                    f"az network lb delete --resource-group {group} --name {name}",
                    net_sdk + f"net.load_balancers.begin_delete('{group}', '{name}').result()", True),
        ]
    if rtype == "natgw":
        net_sdk = ("from azure.identity import DefaultAzureCredential\n"
                   "from azure.mgmt.network import NetworkManagementClient\n"
                   "net = NetworkManagementClient(DefaultAzureCredential(), subscription_id)\n")
        return [
            RemStep(1, "Verify NAT gateway utilization",
                    f"az network nat gateway show --resource-group {group} --name {name}",
                    net_sdk + f"print(net.nat_gateways.get('{group}', '{name}'))", False),
            RemStep(2, "Delete the unused NAT gateway",
                    f"az network nat gateway delete --resource-group {group} --name {name}",
                    net_sdk + f"net.nat_gateways.begin_delete('{group}', '{name}').result()", True),
        ]
    return [RemStep(1, "Manual review required (unrecognized resource type)",
                    f"az resource show --ids {rid}", "# manual review", False)]


def _steps_gcp(rtype: str, rid: str) -> list[RemStep]:
    loc, name = _gcp_parts(rid)
    kind = {"disk": "disks", "vm": "instances", "ip": "addresses",
            "snapshot": "snapshots", "lb": "forwarding-rules",
            "natgw": "routers"}.get(rtype)
    if kind is None:
        return [RemStep(1, "Manual review required (unrecognized resource type)",
                        f"gcloud asset search-all-resources --query 'name:{name}'",
                        "# manual review", False)]
    loc_flag = "" if rtype == "snapshot" else f" {loc}"
    sdk = (f"from google.cloud import compute_v1\n"
           f"# use the matching compute_v1 client for '{kind}'\n")
    return [
        RemStep(1, f"Verify the {rtype} is safe to remove",
                f"gcloud compute {kind} describe {name}{loc_flag}",
                sdk + f"# describe '{name}' and confirm it is unused", False),
        RemStep(2, f"Delete the {rtype}",
                f"gcloud compute {kind} delete {name}{loc_flag} --quiet",
                sdk + f"# delete '{name}'", True),
    ]


_STEPS_BY_PROVIDER = {"aws": _steps_aws, "azure": _steps_azure, "gcp": _steps_gcp}


def _resize_plan(provider: str, rid: str) -> list[RemStep]:
    if provider == "aws":
        return [
            RemStep(1, "Verify sustained low CPU before resizing",
                    f"aws cloudwatch get-metric-statistics --namespace AWS/EC2 "
                    f"--metric-name CPUUtilization --dimensions Name=InstanceId,Value={rid} "
                    f"--statistics Average --period 86400 --start-time $(date -d '-14 days' -Iseconds) "
                    f"--end-time $(date -Iseconds)",
                    f"import boto3\ncw = boto3.client('cloudwatch')\n"
                    f"# fetch 14d average CPUUtilization for '{rid}'", False),
            RemStep(2, "Stop, downsize one instance size, and restart",
                    f"aws ec2 stop-instances --instance-ids {rid} && "
                    f"aws ec2 modify-instance-attribute --instance-id {rid} "
                    f"--instance-type '{{\"Value\": \"<one-size-smaller>\"}}' && "
                    f"aws ec2 start-instances --instance-ids {rid}",
                    f"import boto3\nec2 = boto3.client('ec2')\n"
                    f"ec2.stop_instances(InstanceIds=['{rid}'])\n"
                    f"ec2.get_waiter('instance_stopped').wait(InstanceIds=['{rid}'])\n"
                    f"ec2.modify_instance_attribute(InstanceId='{rid}', "
                    f"InstanceType={{'Value': '<one-size-smaller>'}})\n"
                    f"ec2.start_instances(InstanceIds=['{rid}'])", True),
        ]
    if provider == "azure":
        group, name = _azure_parts(rid)
        return [
            RemStep(1, "List available smaller sizes for this VM",
                    f"az vm list-vm-resize-options --resource-group {group} --name {name} -o table",
                    "# review size options one tier below current", False),
            RemStep(2, "Resize the VM one size down",
                    f"az vm resize --resource-group {group} --name {name} --size <one-size-smaller>",
                    f"# ComputeManagementClient: update hardware_profile.vm_size for '{name}'", True),
        ]
    loc, name = _gcp_parts(rid)
    return [
        RemStep(1, "Verify sustained low CPU before resizing",
                f"gcloud compute instances describe {name} {loc}",
                f"# confirm machine type and utilization for '{name}'", False),
        RemStep(2, "Stop, set a smaller machine type, and restart",
                f"gcloud compute instances stop {name} {loc} && "
                f"gcloud compute instances set-machine-type {name} {loc} "
                f"--machine-type=<one-size-smaller> && "
                f"gcloud compute instances start {name} {loc}",
                f"# compute_v1.InstancesClient: set_machine_type for '{name}'", True),
    ]


def _tagging_plan(provider: str, rid: str) -> list[RemStep]:
    if provider == "aws":
        return [RemStep(1, "Assign an owner tag so this spend is accountable",
                        f"aws ec2 create-tags --resources {rid} "
                        f"--tags Key=owner,Value=<team-name>",
                        f"import boto3\nboto3.client('ec2').create_tags("
                        f"Resources=['{rid}'], Tags=[{{'Key': 'owner', "
                        f"'Value': '<team-name>'}}])", False)]
    if provider == "azure":
        return [RemStep(1, "Assign an owner tag so this spend is accountable",
                        f"az tag update --resource-id {rid} --operation merge "
                        f"--tags owner=<team-name>",
                        "# ResourceManagementClient tags.begin_update_at_scope", False)]
    loc, name = _gcp_parts(rid)
    return [RemStep(1, "Assign an owner label so this spend is accountable",
                    f"gcloud compute instances add-labels {name} {loc} "
                    f"--labels=owner=<team-name>",
                    f"# add label owner=<team-name> to '{name}'", False)]


def build_plan(finding: FindingResult) -> RemediationPlan:
    r = finding.resource
    if finding.rule == "untagged_resource":
        steps = _tagging_plan(r.provider, r.resource_id)
    elif finding.rule == "oversized_vm":
        steps = _resize_plan(r.provider, r.resource_id)
    else:
        builder = _STEPS_BY_PROVIDER.get(r.provider, _steps_aws)
        steps = builder(r.resource_type, r.resource_id)
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
