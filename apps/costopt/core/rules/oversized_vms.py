"""Rule: running VMs with sustained low (but not idle) CPU — rightsizing candidates."""
from __future__ import annotations

from datetime import date

from apps.costopt.core.models import FindingResult, NormalizedResource
from apps.costopt.core.policies import DEFAULTS, severity_for
from apps.costopt.core.registry import rule


@rule("oversized_vm", category="compute")
def evaluate_oversized_vms(resources: list[NormalizedResource],
                           policies: dict | None = None,
                           today: date | None = None) -> list[FindingResult]:
    p = policies or DEFAULTS
    findings = []
    for r in resources:
        if r.resource_type != "vm" or r.state != "running":
            continue
        cpu = r.tags.get("avgCpuPct")
        if cpu is None:
            continue
        cpu = float(cpu)
        if not (p["cpu_idle_threshold_pct"] <= cpu < p["vm_rightsize_cpu_pct"]):
            continue
        savings = round(r.monthly_cost * p["rightsize_saving_fraction"], 2)
        findings.append(FindingResult(
            resource=r, rule="oversized_vm", category="compute",
            severity=severity_for(savings, p),
            est_monthly_savings=savings,
            reason=f"VM averages {cpu:.1f}% CPU (< {p['vm_rightsize_cpu_pct']}%) at "
                   f"${r.monthly_cost:.2f}/mo — downsizing one size saves "
                   f"~{p['rightsize_saving_fraction']:.0%}.",
        ))
    return findings
