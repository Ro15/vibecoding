"""Rule: elastic/public IPs billed while not associated with anything."""
from __future__ import annotations

from datetime import date

from app.core.models import FindingResult, NormalizedResource
from app.core.policies import DEFAULTS, severity_for
from app.core.registry import rule


@rule("orphaned_ip", category="network")
def evaluate_orphaned_ips(resources: list[NormalizedResource],
                          policies: dict | None = None,
                          today: date | None = None) -> list[FindingResult]:
    p = policies or DEFAULTS
    findings = []
    for r in resources:
        if r.resource_type != "ip" or r.state != "unassociated":
            continue
        findings.append(FindingResult(
            resource=r, rule="orphaned_ip", category="network",
            severity=severity_for(r.monthly_cost, p),
            est_monthly_savings=round(r.monthly_cost, 2),
            reason=f"Public/elastic IP is unassociated yet billed ${r.monthly_cost:.2f}/mo "
                   f"(cloud providers charge for idle addresses).",
        ))
    return findings
