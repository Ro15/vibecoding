"""Rule: load balancers billed while serving almost no traffic."""
from __future__ import annotations

from datetime import date

from apps.costopt.core.models import FindingResult, NormalizedResource
from apps.costopt.core.policies import DEFAULTS, severity_for
from apps.costopt.core.registry import rule


@rule("idle_load_balancer", category="network")
def evaluate_idle_load_balancers(resources: list[NormalizedResource],
                                 policies: dict | None = None,
                                 today: date | None = None) -> list[FindingResult]:
    p = policies or DEFAULTS
    findings = []
    for r in resources:
        if r.resource_type != "lb":
            continue
        requests = r.tags.get("requestCount")
        if requests is None:
            continue  # no metric — never false-positive
        requests = float(requests)
        if requests >= p["lb_low_requests"]:
            continue
        findings.append(FindingResult(
            resource=r, rule="idle_load_balancer", category="network",
            severity=severity_for(r.monthly_cost, p),
            est_monthly_savings=round(r.monthly_cost, 2),
            reason=f"Load balancer served {requests:.0f} requests this period "
                   f"(< {p['lb_low_requests']:.0f}) yet costs ${r.monthly_cost:.2f}/mo.",
        ))
    return findings
