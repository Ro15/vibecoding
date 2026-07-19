"""Guardrail domain models. Pure Python."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IacResource:
    address: str            # e.g. "aws_s3_bucket.public" or CFN logical id
    provider: str           # aws | azure | gcp | other
    rtype: str              # normalized: s3_bucket, security_group, rds_instance, ...
    raw_type: str           # original type string
    name: str
    config: dict = field(default_factory=dict)
    source: str = ""        # filename
    source_format: str = "" # hcl | cloudformation | tfplan


@dataclass
class Finding:
    resource: IacResource
    policy: str
    title: str
    severity: str           # critical | high | medium | low
    framework: str          # e.g. "CIS 5.2"
    detail: str
    remediation: str


# raw-type → (provider, normalized rtype)
TYPE_MAP = {
    # AWS Terraform
    "aws_s3_bucket": ("aws", "s3_bucket"),
    "aws_security_group": ("aws", "security_group"),
    "aws_instance": ("aws", "ec2_instance"),
    "aws_db_instance": ("aws", "rds_instance"),
    "aws_ebs_volume": ("aws", "ebs_volume"),
    "aws_iam_policy": ("aws", "iam_policy"),
    "aws_iam_role_policy": ("aws", "iam_policy"),
    # AWS CloudFormation
    "AWS::S3::Bucket": ("aws", "s3_bucket"),
    "AWS::EC2::SecurityGroup": ("aws", "security_group"),
    "AWS::EC2::Instance": ("aws", "ec2_instance"),
    "AWS::RDS::DBInstance": ("aws", "rds_instance"),
    "AWS::EC2::Volume": ("aws", "ebs_volume"),
    "AWS::IAM::Policy": ("aws", "iam_policy"),
}


def classify(raw_type: str) -> tuple[str, str]:
    if raw_type in TYPE_MAP:
        return TYPE_MAP[raw_type]
    if raw_type.startswith("aws_") or raw_type.startswith("AWS::"):
        return ("aws", "other")
    if raw_type.startswith("azurerm_"):
        return ("azure", "other")
    if raw_type.startswith("google_"):
        return ("gcp", "other")
    return ("other", "other")
