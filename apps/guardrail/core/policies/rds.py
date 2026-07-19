"""RDS database policies."""
from __future__ import annotations

from apps.guardrail.core.models import Finding
from apps.guardrail.core.registry import policy


@policy("rds_public", severity="high", framework="CIS 2.3.3", rtypes=["rds_instance"])
def rds_public(resources):
    out = []
    for r in resources:
        if r.config.get("publicly_accessible") is True:
            out.append(Finding(
                resource=r, policy="rds_public", title="RDS instance publicly accessible",
                severity="high", framework="CIS 2.3.3",
                detail=f"Database '{r.name}' is reachable from the public internet.",
                remediation="Set publicly_accessible = false and place the DB in private subnets."))
    return out


@policy("rds_unencrypted", severity="medium", framework="CIS 2.3.1",
        rtypes=["rds_instance"])
def rds_unencrypted(resources):
    out = []
    for r in resources:
        if r.config.get("encrypted") is False:
            out.append(Finding(
                resource=r, policy="rds_unencrypted", title="RDS storage not encrypted",
                severity="medium", framework="CIS 2.3.1",
                detail=f"Database '{r.name}' has storage_encrypted disabled.",
                remediation="Set storage_encrypted = true (requires recreate for existing DBs)."))
    return out
