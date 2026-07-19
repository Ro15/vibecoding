"""Rule: elastic/public IPs billed while not associated with anything."""
from __future__ import annotations

from app.core.models import FindingResult, NormalizedResource
from app.core.registry import rule, severity_for


@rule("orphaned_ip", category="network")
def evaluate_orphaned_ips(resources: list[NormalizedResource]) -> list[FindingResult]:
    findings = []
    for r in resources:
        if r.resource_type != "ip" or r.state != "unassociated":
            continue
        findings.append(FindingResult(
            resource=r,
            rule="orphaned_ip",
            category="network",
            severity=severity_for(r.monthly_cost),
            est_monthly_savings=round(r.monthly_cost, 2),
            reason=f"Public/elastic IP is unassociated yet billed ${r.monthly_cost:.2f}/mo "
                   f"(cloud providers charge for idle addresses).",
        ))
    return findings
