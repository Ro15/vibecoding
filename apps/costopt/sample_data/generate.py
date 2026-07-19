"""Deterministic sample billing exports with seeded waste.

Run:  python sample_data/generate.py
Writes June (current) + May (previous) AWS/Azure exports, a GCP billing export,
and a FOCUS-format export next to this file.
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

SEED = 42
PERIOD = "2026-06"
PREV_PERIOD = "2026-05"
HERE = Path(__file__).parent

AWS_REGIONS = ["us-east-1", "eu-west-1"]
AZ_REGIONS = ["eastus", "westeurope"]

OLD_DATE = "2025-11-02"        # well past 90-day snapshot retention
RECENT_DATE = "2026-06-01"
AGED_STOP_DATE = "2026-04-05"  # stopped > 30 days

AWS_FIELDS = [
    "identity/LineItemId", "lineItem/UsageAccountId", "lineItem/ResourceId",
    "lineItem/ProductCode", "lineItem/UsageType", "lineItem/UsageAmount",
    "lineItem/UnblendedCost", "product/ProductName", "product/region",
    "lineItem/UsageStartDate", "resourceTags/user:Name",
    "resourceTags/user:owner", "resourceTags/aws:attachmentState",
    "resourceTags/aws:createdDate", "resourceTags/aws:cpuAvgPct",
    "resourceTags/aws:requestCount", "resourceTags/aws:dataProcessedGB",
    "resourceTags/aws:stoppedDate",
]


def _aws_row(rng, res_id, product, usage_type, cost, usage, region, name,
             attach_state, created, cpu, owner="team-platform", requests="",
             data_gb="", stopped_date="", period=PERIOD):
    return {
        "identity/LineItemId": f"li-{rng.randrange(10**12):012d}",
        "lineItem/UsageAccountId": "111122223333",
        "lineItem/ResourceId": res_id,
        "lineItem/ProductCode": product,
        "lineItem/UsageType": usage_type,
        "lineItem/UsageAmount": f"{usage:.2f}",
        "lineItem/UnblendedCost": f"{cost:.4f}",
        "product/ProductName": {
            "AmazonEC2": "Amazon Elastic Compute Cloud",
            "AmazonEBS": "Amazon Elastic Block Store",
            "AWSELB": "Elastic Load Balancing",
        }.get(product, product),
        "product/region": region,
        "lineItem/UsageStartDate": f"{period}-01T00:00:00Z",
        "resourceTags/user:Name": name,
        "resourceTags/user:owner": owner,
        "resourceTags/aws:attachmentState": attach_state,
        "resourceTags/aws:createdDate": created,
        "resourceTags/aws:cpuAvgPct": cpu,
        "resourceTags/aws:requestCount": requests,
        "resourceTags/aws:dataProcessedGB": data_gb,
        "resourceTags/aws:stoppedDate": stopped_date,
    }


def generate_aws(rng) -> list[dict]:
    rows = []
    region = lambda: rng.choice(AWS_REGIONS)  # noqa: E731

    # --- seeded waste ---
    for i, cost in enumerate([43.80, 87.50, 8.20]):  # 3 unattached EBS volumes
        rows.append(_aws_row(rng, f"vol-0waste{i:04d}", "AmazonEBS", "EBS:VolumeUsage.gp3",
                             cost, 720, region(), f"orphan-vol-{i}", "available", RECENT_DATE, ""))
    for i, cost in enumerate([62.40, 15.30]):  # 2 stopped-but-billed EC2 (recent stops)
        rows.append(_aws_row(rng, f"i-0stopped{i:04d}", "AmazonEC2", "BoxUsage:m5.large",
                             cost, 720, region(), f"stopped-vm-{i}", "stopped", RECENT_DATE, "0.0"))
    for i in range(3):  # 3 unassociated Elastic IPs
        rows.append(_aws_row(rng, f"eipalloc-0waste{i:04d}", "AmazonEC2", "ElasticIP:IdleAddress",
                             3.60, 720, region(), f"orphan-eip-{i}", "unassociated", RECENT_DATE, ""))
    for i, cost in enumerate([12.75, 55.10, 4.90]):  # 3 old snapshots
        rows.append(_aws_row(rng, f"snap-0old{i:04d}", "AmazonEBS", "EBS:SnapshotUsage",
                             cost, 720, region(), f"old-snap-{i}", "", OLD_DATE, ""))
    for i, (cost, reqs) in enumerate([(16.20, "12"), (22.00, "40")]):  # 2 idle load balancers
        rows.append(_aws_row(rng, f"lb-0idle{i:04d}", "AWSELB", "LoadBalancerUsage",
                             cost, 720, region(), f"idle-lb-{i}", "", RECENT_DATE, "",
                             requests=reqs))
    for i, (cost, gb) in enumerate([(32.85, "0.20"), (32.85, "0.50")]):  # 2 unused NAT gws
        rows.append(_aws_row(rng, f"nat-0unused{i:04d}", "AmazonEC2", "NatGateway-Hours",
                             cost, 720, region(), f"unused-nat-{i}", "", RECENT_DATE, "",
                             data_gb=gb))
    for i, (cost, cpu) in enumerate([(140.00, "22.5"), (90.00, "31.0")]):  # 2 oversized VMs
        rows.append(_aws_row(rng, f"i-0oversz{i:04d}", "AmazonEC2", "BoxUsage:m5.2xlarge",
                             cost, 720, region(), f"oversized-vm-{i}", "running",
                             RECENT_DATE, cpu))
    rows.append(_aws_row(rng, "i-0agedstop0000", "AmazonEC2", "BoxUsage:m5.large",  # aged stop
                         21.50, 720, region(), "aged-stopped-vm-0", "stopped",
                         RECENT_DATE, "0.0", stopped_date=AGED_STOP_DATE))
    # 2 untagged (healthy but unowned — governance finding only)
    rows.append(_aws_row(rng, "vol-0untag0000", "AmazonEBS", "EBS:VolumeUsage.gp3",
                         28.40, 720, region(), "mystery-vol", "attached", RECENT_DATE, "",
                         owner=""))
    rows.append(_aws_row(rng, "i-0untag0000", "AmazonEC2", "BoxUsage:m5.large",
                         95.00, 720, region(), "mystery-vm", "running", RECENT_DATE, "55.0",
                         owner=""))

    # --- healthy noise ---
    for i in range(20):
        rows.append(_aws_row(rng, f"vol-0ok{i:04d}", "AmazonEBS", "EBS:VolumeUsage.gp3",
                             rng.uniform(5, 60), 720, region(), f"app-vol-{i}", "attached",
                             RECENT_DATE, "", owner="team-app" if i % 2 else "team-data"))
    for i in range(12):
        rows.append(_aws_row(rng, f"i-0busy{i:04d}", "AmazonEC2", "BoxUsage:m5.large",
                             rng.uniform(30, 140), 720, region(), f"app-vm-{i}", "running",
                             RECENT_DATE, f"{rng.uniform(45, 85):.1f}",
                             owner="team-app" if i % 2 else "team-data"))
    for i in range(4):
        rows.append(_aws_row(rng, f"eipalloc-0ok{i:04d}", "AmazonEC2", "ElasticIP:Address",
                             0.0, 720, region(), f"app-eip-{i}", "associated", RECENT_DATE, "",
                             owner="team-app"))
    for i in range(6):
        rows.append(_aws_row(rng, f"snap-0new{i:04d}", "AmazonEBS", "EBS:SnapshotUsage",
                             rng.uniform(1, 20), 720, region(), f"backup-{i}", "", RECENT_DATE, "",
                             owner="team-data"))
    rows.append(_aws_row(rng, "lb-0busy0000", "AWSELB", "LoadBalancerUsage",
                         18.90, 720, region(), "app-lb", "", RECENT_DATE, "",
                         owner="team-app", requests="2500000"))
    rows.append(_aws_row(rng, "nat-0used0000", "AmazonEC2", "NatGateway-Hours",
                         45.00, 720, region(), "app-nat", "", RECENT_DATE, "",
                         owner="team-app", data_gb="840"))
    return rows


def generate_aws_prev(rng) -> list[dict]:
    """May export: smaller waste footprint — shows the month-over-month trend."""
    rows = []
    region = lambda: rng.choice(AWS_REGIONS)  # noqa: E731
    for res_id, cost in (("vol-0waste0000", 40.10), ("vol-0waste0001", 85.00)):
        rows.append(_aws_row(rng, res_id, "AmazonEBS", "EBS:VolumeUsage.gp3", cost, 720,
                             region(), "orphan-vol", "available", "2026-05-01", "",
                             period=PREV_PERIOD))
    for i in range(2):
        rows.append(_aws_row(rng, f"eipalloc-0waste{i:04d}", "AmazonEC2",
                             "ElasticIP:IdleAddress", 3.60, 720, region(), f"orphan-eip-{i}",
                             "unassociated", "2026-05-01", "", period=PREV_PERIOD))
    rows.append(_aws_row(rng, "snap-0old0001", "AmazonEBS", "EBS:SnapshotUsage", 54.00, 720,
                         region(), "old-snap-1", "", OLD_DATE, "", period=PREV_PERIOD))
    for i in range(8):
        rows.append(_aws_row(rng, f"vol-0ok{i:04d}", "AmazonEBS", "EBS:VolumeUsage.gp3",
                             rng.uniform(5, 60), 720, region(), f"app-vol-{i}", "attached",
                             "2026-05-01", "", owner="team-app", period=PREV_PERIOD))
    return rows


def _az_item(rng, res_id, res_type, meter_cat, meter_name, cost, qty, loc,
             info: dict, tags: dict, date_str=None):
    return {
        "ResourceId": res_id,
        "ResourceType": res_type,
        "MeterCategory": meter_cat,
        "MeterName": meter_name,
        "CostInBillingCurrency": round(cost, 4),
        "Quantity": round(qty, 2),
        "ResourceLocation": loc,
        "Date": date_str or f"{PERIOD}-01",
        "Tags": json.dumps(tags),
        "AdditionalInfo": json.dumps(info),
    }


def _az_id(sub, rg, provider_path, name):
    return f"/subscriptions/{sub}/resourceGroups/{rg}/providers/{provider_path}/{name}"


SUB = "aaaabbbb-1111-2222-3333-ccccddddeeee"


def generate_azure(rng) -> list[dict]:
    items = []
    loc = lambda: rng.choice(AZ_REGIONS)  # noqa: E731

    # --- seeded waste ---
    for i, cost in enumerate([38.20, 91.00, 6.75]):  # 3 unattached disks
        items.append(_az_item(rng, _az_id(SUB, "rg-app", "Microsoft.Compute/disks", f"orphan-disk-{i}"),
                              "Microsoft.Compute/disks", "Storage", "P10 Disks", cost, 720, loc(),
                              {"attachmentState": "Unattached", "createdDate": RECENT_DATE},
                              {"env": "prod", "owner": "team-platform"}))
    for i, cost in enumerate([71.30, 18.60]):  # 2 idle VMs
        items.append(_az_item(rng, _az_id(SUB, "rg-app", "Microsoft.Compute/virtualMachines", f"idle-vm-{i}"),
                              "Microsoft.Compute/virtualMachines", "Virtual Machines", "D2s v3",
                              cost, 720, loc(),
                              {"powerState": "stopped", "avgCpuPct": 0.4, "createdDate": RECENT_DATE},
                              {"env": "dev", "owner": "team-platform"}))
    for i in range(2):  # 2 unassociated public IPs
        items.append(_az_item(rng, _az_id(SUB, "rg-net", "Microsoft.Network/publicIPAddresses", f"orphan-ip-{i}"),
                              "Microsoft.Network/publicIPAddresses", "Virtual Network",
                              "Static Public IP", 2.90, 720, loc(),
                              {"attachmentState": "Unassociated", "createdDate": RECENT_DATE},
                              {"owner": "team-platform"}))
    for i, cost in enumerate([9.80, 47.20, 3.10]):  # 3 old snapshots
        items.append(_az_item(rng, _az_id(SUB, "rg-backup", "Microsoft.Compute/snapshots", f"old-snap-{i}"),
                              "Microsoft.Compute/snapshots", "Storage", "Snapshots LRS",
                              cost, 720, loc(),
                              {"createdDate": OLD_DATE}, {"owner": "team-platform"}))
    items.append(_az_item(rng, _az_id(SUB, "rg-net", "Microsoft.Network/loadBalancers", "idle-lb-0"),
                          "Microsoft.Network/loadBalancers", "Virtual Network", "Standard LB",
                          19.75, 720, loc(),
                          {"requestCount": 8, "createdDate": RECENT_DATE},
                          {"owner": "team-platform"}))
    items.append(_az_item(rng, _az_id(SUB, "rg-net", "Microsoft.Network/natGateways", "unused-nat-0"),
                          "Microsoft.Network/natGateways", "Virtual Network", "NAT Gateway",
                          29.90, 720, loc(),
                          {"dataProcessedGB": 0.1, "createdDate": RECENT_DATE},
                          {"owner": "team-platform"}))
    items.append(_az_item(rng, _az_id(SUB, "rg-app", "Microsoft.Compute/virtualMachines", "oversize-vm-0"),
                          "Microsoft.Compute/virtualMachines", "Virtual Machines", "D8s v3",
                          120.00, 720, loc(),
                          {"powerState": "running", "avgCpuPct": 24.0, "createdDate": RECENT_DATE},
                          {"owner": "team-app"}))
    items.append(_az_item(rng, _az_id(SUB, "rg-app", "Microsoft.Compute/disks", "untag-disk-0"),
                          "Microsoft.Compute/disks", "Storage", "P10 Disks", 24.60, 720, loc(),
                          {"attachmentState": "Attached", "createdDate": RECENT_DATE},
                          {"env": "prod"}))  # no owner — governance finding

    # --- healthy noise ---
    for i in range(14):
        items.append(_az_item(rng, _az_id(SUB, "rg-app", "Microsoft.Compute/disks", f"app-disk-{i}"),
                              "Microsoft.Compute/disks", "Storage", "P10 Disks",
                              rng.uniform(4, 55), 720, loc(),
                              {"attachmentState": "Attached", "createdDate": RECENT_DATE},
                              {"env": "prod", "owner": "team-app" if i % 2 else "team-data"}))
    for i in range(9):
        items.append(_az_item(rng, _az_id(SUB, "rg-app", "Microsoft.Compute/virtualMachines", f"app-vm-{i}"),
                              "Microsoft.Compute/virtualMachines", "Virtual Machines", "D2s v3",
                              rng.uniform(40, 160), 720, loc(),
                              {"powerState": "running", "avgCpuPct": rng.uniform(45, 80),
                               "createdDate": RECENT_DATE},
                              {"env": "prod", "owner": "team-app" if i % 2 else "team-data"}))
    for i in range(3):
        items.append(_az_item(rng, _az_id(SUB, "rg-net", "Microsoft.Network/publicIPAddresses", f"app-ip-{i}"),
                              "Microsoft.Network/publicIPAddresses", "Virtual Network",
                              "Static Public IP", 2.90, 720, loc(),
                              {"attachmentState": "Associated", "createdDate": RECENT_DATE},
                              {"owner": "team-app"}))
    for i in range(5):
        items.append(_az_item(rng, _az_id(SUB, "rg-backup", "Microsoft.Compute/snapshots", f"new-snap-{i}"),
                              "Microsoft.Compute/snapshots", "Storage", "Snapshots LRS",
                              rng.uniform(1, 15), 720, loc(),
                              {"createdDate": RECENT_DATE}, {"owner": "team-data"}))
    items.append(_az_item(rng, _az_id(SUB, "rg-net", "Microsoft.Network/loadBalancers", "app-lb-0"),
                          "Microsoft.Network/loadBalancers", "Virtual Network", "Standard LB",
                          21.00, 720, loc(),
                          {"requestCount": 500000, "createdDate": RECENT_DATE},
                          {"owner": "team-app"}))
    items.append(_az_item(rng, _az_id(SUB, "rg-net", "Microsoft.Network/natGateways", "app-nat-0"),
                          "Microsoft.Network/natGateways", "Virtual Network", "NAT Gateway",
                          33.00, 720, loc(),
                          {"dataProcessedGB": 300, "createdDate": RECENT_DATE},
                          {"owner": "team-app"}))
    return items


def generate_azure_prev(rng) -> list[dict]:
    items = []
    loc = lambda: rng.choice(AZ_REGIONS)  # noqa: E731
    date_str = f"{PREV_PERIOD}-01"
    for i, cost in enumerate([36.50, 89.00]):
        items.append(_az_item(rng, _az_id(SUB, "rg-app", "Microsoft.Compute/disks", f"orphan-disk-{i}"),
                              "Microsoft.Compute/disks", "Storage", "P10 Disks", cost, 720, loc(),
                              {"attachmentState": "Unattached", "createdDate": date_str},
                              {"owner": "team-platform"}, date_str=date_str))
    items.append(_az_item(rng, _az_id(SUB, "rg-app", "Microsoft.Compute/virtualMachines", "idle-vm-0"),
                          "Microsoft.Compute/virtualMachines", "Virtual Machines", "D2s v3",
                          69.80, 720, loc(),
                          {"powerState": "stopped", "avgCpuPct": 0.3, "createdDate": date_str},
                          {"owner": "team-platform"}, date_str=date_str))
    for i in range(5):
        items.append(_az_item(rng, _az_id(SUB, "rg-app", "Microsoft.Compute/disks", f"app-disk-{i}"),
                              "Microsoft.Compute/disks", "Storage", "P10 Disks",
                              rng.uniform(4, 55), 720, loc(),
                              {"attachmentState": "Attached", "createdDate": date_str},
                              {"owner": "team-app"}, date_str=date_str))
    return items


def _gcp_item(name, service, sku, cost, usage, region, labels: dict):
    return {
        "resource": {"name": name},
        "service": {"description": service},
        "sku": {"description": sku},
        "cost": round(cost, 4),
        "usage": {"amount": usage, "unit": "hour"},
        "location": {"region": region},
        "labels": [{"key": k, "value": str(v)} for k, v in labels.items()],
        "usage_start_time": f"{PERIOD}-01T00:00:00Z",
    }


def generate_gcp(rng) -> list[dict]:
    z = "projects/demo-project/zones/us-central1-a"
    g = "projects/demo-project/global"
    items = [
        # --- seeded waste (6 findings) ---
        _gcp_item(f"{z}/disks/orphan-disk-0", "Compute Engine", "Storage PD Capacity",
                  27.30, 720, "us-central1",
                  {"attachment_state": "unattached", "owner": "team-ml",
                   "created_date": RECENT_DATE}),
        _gcp_item(f"{z}/instances/idle-vm-0", "Compute Engine", "N1 Instance Core",
                  52.00, 720, "us-central1",
                  {"power_state": "stopped", "owner": "team-ml", "created_date": RECENT_DATE}),
        _gcp_item(f"{g}/addresses/orphan-ip-0", "Compute Engine", "Static Ip Charge",
                  2.92, 720, "us-central1",
                  {"attachment_state": "unassociated", "owner": "team-ml"}),
        _gcp_item(f"{g}/snapshots/old-snap-0", "Compute Engine", "Storage PD Snapshot",
                  11.40, 720, "us-central1",
                  {"created_date": OLD_DATE, "owner": "team-ml"}),
        _gcp_item(f"{z}/instances/oversized-vm-0", "Compute Engine", "N1 Instance Core",
                  88.00, 720, "us-central1",
                  {"power_state": "running", "avg_cpu_pct": 25.0, "owner": "team-ml",
                   "created_date": RECENT_DATE}),
        _gcp_item(f"{z}/instances/mystery-vm-0", "Compute Engine", "N1 Instance Core",
                  61.00, 720, "us-central1",
                  {"power_state": "running", "avg_cpu_pct": 60.0,
                   "created_date": RECENT_DATE}),  # no owner — governance finding
        # --- healthy noise ---
        _gcp_item(f"{z}/disks/app-disk-0", "Compute Engine", "Storage PD Capacity",
                  18.10, 720, "us-central1",
                  {"attachment_state": "attached", "owner": "team-web",
                   "created_date": RECENT_DATE}),
        _gcp_item(f"{z}/disks/app-disk-1", "Compute Engine", "Storage PD Capacity",
                  9.75, 720, "us-central1",
                  {"attachment_state": "attached", "owner": "team-web",
                   "created_date": RECENT_DATE}),
        _gcp_item(f"{z}/instances/app-vm-0", "Compute Engine", "N1 Instance Core",
                  104.00, 720, "us-central1",
                  {"power_state": "running", "avg_cpu_pct": 72.0, "owner": "team-web",
                   "created_date": RECENT_DATE}),
        _gcp_item(f"{z}/instances/app-vm-1", "Compute Engine", "N1 Instance Core",
                  97.50, 720, "us-central1",
                  {"power_state": "running", "avg_cpu_pct": 64.0, "owner": "team-web",
                   "created_date": RECENT_DATE}),
        _gcp_item(f"{g}/addresses/app-ip-0", "Compute Engine", "Static Ip Charge",
                  0.0, 720, "us-central1",
                  {"attachment_state": "associated", "owner": "team-web"}),
        _gcp_item(f"{g}/snapshots/new-snap-0", "Compute Engine", "Storage PD Snapshot",
                  4.20, 720, "us-central1",
                  {"created_date": RECENT_DATE, "owner": "team-web"}),
    ]
    return items


FOCUS_FIELDS = ["ProviderName", "ResourceId", "ResourceName", "ResourceType",
                "ServiceName", "BilledCost", "ConsumedQuantity", "RegionId",
                "ChargePeriodStart", "Tags"]


def generate_focus() -> list[dict]:
    def row(provider, rid, rname, rtype, service, cost, qty, region, tags):
        return {"ProviderName": provider, "ResourceId": rid, "ResourceName": rname,
                "ResourceType": rtype, "ServiceName": service,
                "BilledCost": f"{cost:.4f}", "ConsumedQuantity": f"{qty:.2f}",
                "RegionId": region, "ChargePeriodStart": f"{PERIOD}-01T00:00:00Z",
                "Tags": json.dumps(tags)}
    return [
        row("AWS", "vol-focus0001", "focus-orphan-vol", "Storage Volume", "Amazon EBS",
            18.50, 720, "us-east-1", {"owner": "team-focus", "x_state": "unattached"}),
        row("AWS", "snap-focus0001", "focus-old-snap", "Snapshot", "Amazon EBS",
            6.20, 720, "us-east-1", {"owner": "team-focus", "x_createdDate": "2025-10-01"}),
        row("Microsoft Azure",
            f"/subscriptions/{SUB}/resourceGroups/rg-app/providers/Microsoft.Compute/virtualMachines/focus-vm-2",
            "focus-vm-2", "Virtual Machine", "Virtual Machines", 12.00, 720, "eastus",
            {"owner": "team-focus", "x_state": "stopped"}),
        row("Microsoft Azure",
            f"/subscriptions/{SUB}/resourceGroups/rg-app/providers/Microsoft.Compute/disks/focus-disk-1",
            "focus-disk-1", "Storage Volume", "Storage", 22.10, 720, "eastus",
            {"owner": "team-focus", "x_state": "attached"}),
        row("Google Cloud", "projects/demo-project/global/addresses/focus-ip-1",
            "focus-ip-1", "Public IP Address", "Compute Engine", 2.90, 720, "us-central1",
            {"owner": "team-focus", "x_state": "unassociated"}),
        row("Google Cloud", "projects/demo-project/zones/us-central1-a/instances/focus-vm-1",
            "focus-vm-1", "Virtual Machine", "Compute Engine", 84.00, 720, "us-central1",
            {"owner": "team-focus", "x_state": "running", "avgCpuPct": 70}),
    ]


def _write_csv(path: Path, rows: list[dict], fields: list[str]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    rng = random.Random(SEED)
    aws_rows = generate_aws(rng)
    _write_csv(HERE / "aws_cur.csv", aws_rows, AWS_FIELDS)
    aws_prev = generate_aws_prev(rng)
    _write_csv(HERE / "aws_cur_prev.csv", aws_prev, AWS_FIELDS)

    azure_items = generate_azure(rng)
    (HERE / "azure_costs.json").write_text(json.dumps(azure_items, indent=1), encoding="utf-8")
    azure_prev = generate_azure_prev(rng)
    (HERE / "azure_costs_prev.json").write_text(json.dumps(azure_prev, indent=1), encoding="utf-8")

    gcp_items = generate_gcp(rng)
    (HERE / "gcp_billing.json").write_text(json.dumps(gcp_items, indent=1), encoding="utf-8")

    focus_rows = generate_focus()
    _write_csv(HERE / "focus_costs.csv", focus_rows, FOCUS_FIELDS)

    print(f"wrote {len(aws_rows)} AWS rows (+{len(aws_prev)} prev), "
          f"{len(azure_items)} Azure items (+{len(azure_prev)} prev), "
          f"{len(gcp_items)} GCP items, {len(focus_rows)} FOCUS rows")


if __name__ == "__main__":
    main()
