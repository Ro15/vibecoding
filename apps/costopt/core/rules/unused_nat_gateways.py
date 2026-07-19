"""Rule: NAT gateways billed hourly while processing almost no data."""
from __future__ import annotations

from datetime import date

from apps.costopt.core.models import FindingResult, NormalizedResource
from apps.costopt.core.policies import DEFAULTS, severity_for
from apps.costopt.core.registry import rule


@rule("unused_nat_gateway", category="network")
def evaluate_unused_nat_gateways(resources: list[NormalizedResource],
                                 policies: dict | None = None,
                                 today: date | None = None) -> list[FindingResult]:
    p = policies or DEFAULTS
    findings = []
    for r in resources:
        if r.resource_type != "natgw":
            continue
        gb = r.tags.get("dataProcessedGB")
        if gb is None:
            continue
        gb = float(gb)
        if gb >= p["natgw_low_gb"]:
            continue
        findings.append(FindingResult(
            resource=r, rule="unused_nat_gateway", category="network",
            severity=severity_for(r.monthly_cost, p),
            est_monthly_savings=round(r.monthly_cost, 2),
            reason=f"NAT gateway processed {gb:.2f} GB this period "
                   f"(< {p['natgw_low_gb']} GB) yet costs ${r.monthly_cost:.2f}/mo "
                   f"in hourly charges.",
        ))
    return findings
