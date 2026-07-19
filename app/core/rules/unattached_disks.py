"""Rule: disks billed while not attached to any compute instance."""
from __future__ import annotations

from app.core.models import FindingResult, NormalizedResource
from app.core.registry import rule, severity_for

UNATTACHED_STATES = {"available", "unattached"}


@rule("unattached_disk", category="storage")
def evaluate_unattached_disks(resources: list[NormalizedResource]) -> list[FindingResult]:
    findings = []
    for r in resources:
        if r.resource_type != "disk" or r.state not in UNATTACHED_STATES:
            continue
        findings.append(FindingResult(
            resource=r,
            rule="unattached_disk",
            category="storage",
            severity=severity_for(r.monthly_cost),
            est_monthly_savings=round(r.monthly_cost, 2),
            reason=f"Disk is billed ${r.monthly_cost:.2f}/mo but its state is "
                   f"'{r.state}' — not attached to any instance.",
        ))
    return findings
