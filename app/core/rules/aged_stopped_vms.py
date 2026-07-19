"""Rule: VMs stopped for longer than the policy threshold — terminate candidates."""
from __future__ import annotations

from datetime import date, datetime

from app.core.models import FindingResult, NormalizedResource
from app.core.policies import DEFAULTS, severity_for
from app.core.registry import rule


@rule("aged_stopped_vm", category="compute")
def evaluate_aged_stopped_vms(resources: list[NormalizedResource],
                              policies: dict | None = None,
                              today: date | None = None) -> list[FindingResult]:
    p = policies or DEFAULTS
    today = today or date.today()
    findings = []
    for r in resources:
        if r.resource_type != "vm" or r.state != "stopped" or r.monthly_cost <= 0:
            continue
        raw = r.tags.get("stoppedDate")
        if not raw:
            continue
        try:
            stopped = datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        age = (today - stopped).days
        if age <= p["stopped_vm_age_days"]:
            continue
        findings.append(FindingResult(
            resource=r, rule="aged_stopped_vm", category="compute",
            severity=severity_for(r.monthly_cost, p),
            est_monthly_savings=round(r.monthly_cost, 2),
            reason=f"VM has been stopped for {age} days "
                   f"(> {p['stopped_vm_age_days']}) while costing "
                   f"${r.monthly_cost:.2f}/mo — terminate and keep an image instead.",
        ))
    return findings
