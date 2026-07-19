"""EBS volume policies."""
from __future__ import annotations

from apps.guardrail.core.models import Finding
from apps.guardrail.core.registry import policy


@policy("ebs_unencrypted", severity="medium", framework="CIS 2.2.1", rtypes=["ebs_volume"])
def ebs_unencrypted(resources):
    out = []
    for r in resources:
        if r.config.get("encrypted") is False:
            out.append(Finding(
                resource=r, policy="ebs_unencrypted", title="EBS volume not encrypted",
                severity="medium", framework="CIS 2.2.1",
                detail=f"Volume '{r.name}' has encryption disabled.",
                remediation="Set encrypted = true (or enable account-level EBS encryption by default)."))
    return out
