from datetime import date
from pathlib import Path

from app.core.providers.aws import parse_aws

SAMPLE = (Path(__file__).parents[2] / "sample_data" / "aws_cur.csv").read_bytes()

HEADER = ("identity/LineItemId,lineItem/UsageAccountId,lineItem/ResourceId,lineItem/ProductCode,"
          "lineItem/UsageType,lineItem/UsageAmount,lineItem/UnblendedCost,product/ProductName,"
          "product/region,lineItem/UsageStartDate,resourceTags/user:Name,"
          "resourceTags/aws:attachmentState,resourceTags/aws:createdDate,resourceTags/aws:cpuAvgPct")


def csv_bytes(*rows):
    return ("\n".join([HEADER, *rows])).encode()


def test_parses_sample_file_without_errors():
    resources, errors = parse_aws(SAMPLE)
    assert errors == []
    assert len(resources) == 53
    assert all(r.provider == "aws" for r in resources)


def test_type_mapping_and_state():
    resources, _ = parse_aws(SAMPLE)
    by_id = {r.resource_id: r for r in resources}
    assert by_id["vol-0waste0000"].resource_type == "disk"
    assert by_id["vol-0waste0000"].state == "available"
    assert by_id["i-0stopped0000"].resource_type == "vm"
    assert by_id["i-0stopped0000"].state == "stopped"
    assert by_id["eipalloc-0waste0000"].resource_type == "ip"
    assert by_id["eipalloc-0waste0000"].state == "unassociated"
    assert by_id["snap-0old0000"].resource_type == "snapshot"
    assert by_id["snap-0old0000"].created_at == date(2025, 11, 2)


def test_aggregates_multiple_rows_per_resource():
    data = csv_bytes(
        "a,acc,vol-1,AmazonEBS,EBS:VolumeUsage.gp3,10,5.0,EBS,us-east-1,2026-06-01T00:00:00Z,n,available,2026-06-01,",
        "b,acc,vol-1,AmazonEBS,EBS:VolumeUsage.gp3,10,7.0,EBS,us-east-1,2026-06-01T00:00:00Z,n,available,2026-06-01,",
    )
    resources, errors = parse_aws(data)
    assert errors == []
    assert len(resources) == 1
    assert resources[0].monthly_cost == 12.0


def test_bad_rows_collected_not_fatal():
    data = csv_bytes(
        "a,acc,,AmazonEBS,EBS:VolumeUsage.gp3,10,5.0,EBS,us-east-1,2026-06-01T00:00:00Z,n,available,2026-06-01,",
        "b,acc,vol-2,AmazonEBS,EBS:VolumeUsage.gp3,10,notanumber,EBS,us-east-1,2026-06-01T00:00:00Z,n,available,2026-06-01,",
        "c,acc,vol-3,AmazonEBS,EBS:VolumeUsage.gp3,10,3.0,EBS,us-east-1,2026-06-01T00:00:00Z,n,available,2026-06-01,",
    )
    resources, errors = parse_aws(data)
    assert len(resources) == 1
    assert resources[0].resource_id == "vol-3"
    assert len(errors) == 2
    assert all("line" in e and "reason" in e for e in errors)


def test_missing_state_tag_degrades_to_unknown():
    data = csv_bytes(
        "a,acc,i-9,AmazonEC2,BoxUsage:m5.large,720,50.0,EC2,us-east-1,2026-06-01T00:00:00Z,n,,,",
    )
    resources, _ = parse_aws(data)
    assert resources[0].state == "unknown"


def test_billing_period_derived_from_usage_start():
    resources, _ = parse_aws(SAMPLE)
    assert all(r.billing_period == "2026-06" for r in resources)
