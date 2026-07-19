"""S3 bucket security policies."""
from __future__ import annotations

from apps.guardrail.core.models import Finding
from apps.guardrail.core.registry import policy

PUBLIC_ACLS = {"public-read", "public-read-write"}


@policy("s3_public_acl", severity="high", framework="CIS 2.1.5", rtypes=["s3_bucket"])
def s3_public_acl(resources):
    out = []
    for r in resources:
        if r.config.get("acl") in PUBLIC_ACLS:
            out.append(Finding(
                resource=r, policy="s3_public_acl", title="Public S3 bucket ACL",
                severity="high", framework="CIS 2.1.5",
                detail=f"Bucket '{r.name}' has ACL '{r.config['acl']}', exposing it publicly.",
                remediation="Set acl = \"private\" and add an aws_s3_bucket_public_access_block."))
    return out


@policy("s3_no_encryption", severity="medium", framework="CIS 2.1.1", rtypes=["s3_bucket"])
def s3_no_encryption(resources):
    out = []
    for r in resources:
        if r.config.get("encrypted") is False:
            out.append(Finding(
                resource=r, policy="s3_no_encryption", title="S3 bucket not encrypted at rest",
                severity="medium", framework="CIS 2.1.1",
                detail=f"Bucket '{r.name}' has no server-side encryption configured.",
                remediation="Add a server_side_encryption_configuration (SSE-S3 or SSE-KMS)."))
    return out


@policy("s3_no_versioning", severity="low", framework="CIS 2.1.3", rtypes=["s3_bucket"])
def s3_no_versioning(resources):
    out = []
    for r in resources:
        if r.config.get("versioning") is False:
            out.append(Finding(
                resource=r, policy="s3_no_versioning", title="S3 bucket versioning disabled",
                severity="low", framework="CIS 2.1.3",
                detail=f"Bucket '{r.name}' has versioning disabled; deletions are unrecoverable.",
                remediation="Enable versioning_configuration { status = \"Enabled\" }."))
    return out
