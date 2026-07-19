"""Rule: VMs billed while stopped, or running with near-zero CPU.

Stopped VMs whose stoppedDate exceeds the aged threshold are left to the
aged_stopped_vm rule (terminate recommendation) to avoid double-counting.
"""
from __future__ import annotations

from datetime import date, datetime

from apps.costopt.core.models import FindingResult, NormalizedResource
from apps.costopt.core.policies import DEFAULTS, severity_for
from apps.costopt.core.registry import rule


def _stopped_age_days(r: NormalizedResource, today: date) -> int | None:
    raw = r.tags.get("stoppedDate")
    if not raw:
        return None
    try:
        stopped = datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (today - stopped).days


@rule("idle_vm", category="compute")
def evaluate_idle_vms(resources: list[NormalizedResource],
                      policies: dict | None = None,
                      today: date | None = None) -> list[FindingResult]:
    p = policies or DEFAULTS
    today = today or date.today()
    findings = []
    for r in resources:
        if r.resource_type != "vm":
            continue
        reason = None
        if r.state == "stopped" and r.monthly_cost > 0:
            age = _stopped_age_days(r, today)
            if age is not None and age > p["stopped_vm_age_days"]:
                continue  # aged_stopped_vm owns this one
            reason = (f"VM is stopped but still incurring ${r.monthly_cost:.2f}/mo "
                      f"(storage/IP charges continue while stopped).")
        else:
            cpu = r.tags.get("avgCpuPct")
            if cpu is not None and float(cpu) < p["cpu_idle_threshold_pct"] and r.usage_hours > 0:
                reason = (f"VM ran {r.usage_hours:.0f}h with average CPU {float(cpu):.1f}% "
                          f"(< {p['cpu_idle_threshold_pct']}%) — effectively idle at "
                          f"${r.monthly_cost:.2f}/mo.")
        if reason is None:
            continue
        findings.append(FindingResult(
            resource=r, rule="idle_vm", category="compute",
            severity=severity_for(r.monthly_cost, p),
            est_monthly_savings=round(r.monthly_cost, 2), reason=reason))
    return findings
