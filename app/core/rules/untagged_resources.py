"""Rule: resources above a cost floor with no ownership tag — governance gap."""
from __future__ import annotations

from datetime import date

from app.core.models import FindingResult, NormalizedResource
from app.core.policies import DEFAULTS
from app.core.registry import rule


@rule("untagged_resource", category="governance")
def evaluate_untagged_resources(resources: list[NormalizedResource],
                                policies: dict | None = None,
                                today: date | None = None) -> list[FindingResult]:
    p = policies or DEFAULTS
    owner_keys = [k.strip() for k in str(p["owner_tag_keys"]).split(",") if k.strip()]
    findings = []
    for r in resources:
        if r.monthly_cost < p["untagged_min_cost_usd"]:
            continue
        if any(r.tags.get(k) for k in owner_keys):
            continue
        findings.append(FindingResult(
            resource=r, rule="untagged_resource", category="governance",
            severity="low",
            est_monthly_savings=0.0,
            reason=f"Resource costs ${r.monthly_cost:.2f}/mo but carries none of the "
                   f"ownership tags ({', '.join(owner_keys)}) — nobody is accountable "
                   f"for this spend.",
        ))
    return findings
