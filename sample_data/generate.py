"""Deterministic sample billing exports with seeded waste.

Run:  python sample_data/generate.py
Writes aws_cur.csv and azure_costs.json next to this file.
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

SEED = 42
BILLING_PERIOD = "2026-06"
HERE = Path(__file__).parent

AWS_REGIONS = ["us-east-1", "eu-west-1"]
AZ_REGIONS = ["eastus", "westeurope"]

# creation dates: old = well past the 90-day snapshot threshold relative to mid-2026
OLD_DATE = "2025-11-02"
RECENT_DATE = "2026-06-01"


def _aws_row(rng, res_id, product, usage_type, cost, usage, region, name, attach_state, created, cpu):
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
        }.get(product, product),
        "product/region": region,
        "lineItem/UsageStartDate": f"{BILLING_PERIOD}-01T00:00:00Z",
        "resourceTags/user:Name": name,
        "resourceTags/aws:attachmentState": attach_state,
        "resourceTags/aws:createdDate": created,
        "resourceTags/aws:cpuAvgPct": cpu,
    }


def generate_aws(rng) -> list[dict]:
    rows = []
    region = lambda: rng.choice(AWS_REGIONS)  # noqa: E731

    # --- seeded waste ---
    # 3 unattached EBS volumes
    for i, cost in enumerate([43.80, 87.50, 8.20]):
        rows.append(_aws_row(rng, f"vol-0waste{i:04d}", "AmazonEBS", "EBS:VolumeUsage.gp3",
                             cost, 720, region(), f"orphan-vol-{i}", "available", RECENT_DATE, ""))
    # 2 stopped-but-billed EC2 instances (storage/EIP charges continue)
    for i, cost in enumerate([62.40, 15.30]):
        rows.append(_aws_row(rng, f"i-0stopped{i:04d}", "AmazonEC2", "BoxUsage:m5.large",
                             cost, 720, region(), f"stopped-vm-{i}", "stopped", RECENT_DATE, "0.0"))
    # 3 unassociated Elastic IPs
    for i in range(3):
        rows.append(_aws_row(rng, f"eipalloc-0waste{i:04d}", "AmazonEC2", "ElasticIP:IdleAddress",
                             3.60, 720, region(), f"orphan-eip-{i}", "unassociated", RECENT_DATE, ""))
    # 3 old snapshots (>90 days)
    for i, cost in enumerate([12.75, 55.10, 4.90]):
        rows.append(_aws_row(rng, f"snap-0old{i:04d}", "AmazonEBS", "EBS:SnapshotUsage",
                             cost, 720, region(), f"old-snap-{i}", "", OLD_DATE, ""))

    # --- healthy noise ---
    for i in range(20):  # attached volumes
        rows.append(_aws_row(rng, f"vol-0ok{i:04d}", "AmazonEBS", "EBS:VolumeUsage.gp3",
                             rng.uniform(5, 60), 720, region(), f"app-vol-{i}", "attached", RECENT_DATE, ""))
    for i in range(12):  # busy instances
        rows.append(_aws_row(rng, f"i-0busy{i:04d}", "AmazonEC2", "BoxUsage:m5.large",
                             rng.uniform(30, 140), 720, region(), f"app-vm-{i}", "running",
                             RECENT_DATE, f"{rng.uniform(20, 85):.1f}"))
    for i in range(4):  # associated EIPs (no idle charge pattern, cost 0)
        rows.append(_aws_row(rng, f"eipalloc-0ok{i:04d}", "AmazonEC2", "ElasticIP:Address",
                             0.0, 720, region(), f"app-eip-{i}", "associated", RECENT_DATE, ""))
    for i in range(6):  # recent snapshots
        rows.append(_aws_row(rng, f"snap-0new{i:04d}", "AmazonEBS", "EBS:SnapshotUsage",
                             rng.uniform(1, 20), 720, region(), f"backup-{i}", "", RECENT_DATE, ""))
    return rows


def _az_item(rng, res_id, res_type, meter_cat, meter_name, cost, qty, loc, info: dict, tags: dict):
    return {
        "ResourceId": res_id,
        "ResourceType": res_type,
        "MeterCategory": meter_cat,
        "MeterName": meter_name,
        "CostInBillingCurrency": round(cost, 4),
        "Quantity": round(qty, 2),
        "ResourceLocation": loc,
        "Date": f"{BILLING_PERIOD}-01",
        "Tags": json.dumps(tags),
        "AdditionalInfo": json.dumps(info),
    }


def _az_id(sub, rg, provider_path, name):
    return f"/subscriptions/{sub}/resourceGroups/{rg}/providers/{provider_path}/{name}"


def generate_azure(rng) -> list[dict]:
    items = []
    sub = "aaaabbbb-1111-2222-3333-ccccddddeeee"
    loc = lambda: rng.choice(AZ_REGIONS)  # noqa: E731

    # --- seeded waste ---
    for i, cost in enumerate([38.20, 91.00, 6.75]):  # 3 unattached managed disks
        items.append(_az_item(rng, _az_id(sub, "rg-app", "Microsoft.Compute/disks", f"orphan-disk-{i}"),
                              "Microsoft.Compute/disks", "Storage", "P10 Disks", cost, 720, loc(),
                              {"attachmentState": "Unattached", "createdDate": RECENT_DATE}, {"env": "prod"}))
    for i, cost in enumerate([71.30, 18.60]):  # 2 idle VMs
        items.append(_az_item(rng, _az_id(sub, "rg-app", "Microsoft.Compute/virtualMachines", f"idle-vm-{i}"),
                              "Microsoft.Compute/virtualMachines", "Virtual Machines", "D2s v3", cost, 720, loc(),
                              {"powerState": "stopped", "avgCpuPct": 0.4, "createdDate": RECENT_DATE}, {"env": "dev"}))
    for i in range(2):  # 2 unassociated public IPs
        items.append(_az_item(rng, _az_id(sub, "rg-net", "Microsoft.Network/publicIPAddresses", f"orphan-ip-{i}"),
                              "Microsoft.Network/publicIPAddresses", "Virtual Network", "Static Public IP",
                              2.90, 720, loc(),
                              {"attachmentState": "Unassociated", "createdDate": RECENT_DATE}, {}))
    for i, cost in enumerate([9.80, 47.20, 3.10]):  # 3 old snapshots
        items.append(_az_item(rng, _az_id(sub, "rg-backup", "Microsoft.Compute/snapshots", f"old-snap-{i}"),
                              "Microsoft.Compute/snapshots", "Storage", "Snapshots LRS", cost, 720, loc(),
                              {"createdDate": OLD_DATE}, {"retention": "unknown"}))

    # --- healthy noise ---
    for i in range(14):
        items.append(_az_item(rng, _az_id(sub, "rg-app", "Microsoft.Compute/disks", f"app-disk-{i}"),
                              "Microsoft.Compute/disks", "Storage", "P10 Disks", rng.uniform(4, 55), 720, loc(),
                              {"attachmentState": "Attached", "createdDate": RECENT_DATE}, {"env": "prod"}))
    for i in range(9):
        items.append(_az_item(rng, _az_id(sub, "rg-app", "Microsoft.Compute/virtualMachines", f"app-vm-{i}"),
                              "Microsoft.Compute/virtualMachines", "Virtual Machines", "D2s v3",
                              rng.uniform(40, 160), 720, loc(),
                              {"powerState": "running", "avgCpuPct": rng.uniform(15, 80),
                               "createdDate": RECENT_DATE}, {"env": "prod"}))
    for i in range(3):
        items.append(_az_item(rng, _az_id(sub, "rg-net", "Microsoft.Network/publicIPAddresses", f"app-ip-{i}"),
                              "Microsoft.Network/publicIPAddresses", "Virtual Network", "Static Public IP",
                              2.90, 720, loc(),
                              {"attachmentState": "Associated", "createdDate": RECENT_DATE}, {}))
    for i in range(5):
        items.append(_az_item(rng, _az_id(sub, "rg-backup", "Microsoft.Compute/snapshots", f"new-snap-{i}"),
                              "Microsoft.Compute/snapshots", "Storage", "Snapshots LRS",
                              rng.uniform(1, 15), 720, loc(),
                              {"createdDate": RECENT_DATE}, {}))
    return items


def main():
    rng = random.Random(SEED)
    aws_rows = generate_aws(rng)
    with open(HERE / "aws_cur.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(aws_rows[0].keys()))
        writer.writeheader()
        writer.writerows(aws_rows)

    azure_items = generate_azure(rng)
    with open(HERE / "azure_costs.json", "w", encoding="utf-8") as f:
        json.dump(azure_items, f, indent=1)

    print(f"wrote {len(aws_rows)} AWS rows, {len(azure_items)} Azure items")


if __name__ == "__main__":
    main()
