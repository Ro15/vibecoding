"""Rule: VMs billed while stopped, or running with near-zero CPU."""
from __future__ import annotations

from app.core.models import FindingResult, NormalizedResource
from app.core.registry import rule, severity_for

CPU_IDLE_THRESHOLD_PCT = 3.0


@rule("idle_vm", category="compute")
def evaluate_idle_vms(resources: list[NormalizedResource]) -> list[FindingResult]:
    findings = []
    for r in resources:
        if r.resource_type != "vm":
            continue
        reason = None
        if r.state == "stopped" and r.monthly_cost > 0:
            reason = (f"VM is stopped but still incurring ${r.monthly_cost:.2f}/mo "
                      f"(storage/IP charges continue while stopped).")
        else:
            cpu = r.tags.get("avgCpuPct")
            if cpu is not None and float(cpu) < CPU_IDLE_THRESHOLD_PCT and r.usage_hours > 0:
                reason = (f"VM ran {r.usage_hours:.0f}h with average CPU {float(cpu):.1f}% "
                          f"(< {CPU_IDLE_THRESHOLD_PCT}%) — effectively idle at ${r.monthly_cost:.2f}/mo.")
        if reason is None:
            continue
        findings.append(FindingResult(
            resource=r,
            rule="idle_vm",
            category="compute",
            severity=severity_for(r.monthly_cost),
            est_monthly_savings=round(r.monthly_cost, 2),
            reason=reason,
        ))
    return findings
