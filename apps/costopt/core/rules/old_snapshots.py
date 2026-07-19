"""Rule: snapshots older than the retention threshold (policy-driven)."""
from __future__ import annotations

from datetime import date

from apps.costopt.core.models import FindingResult, NormalizedResource
from apps.costopt.core.policies import DEFAULTS, severity_for
from apps.costopt.core.registry import rule


@rule("old_snapshot", category="storage")
def evaluate_old_snapshots(resources: list[NormalizedResource],
                           policies: dict | None = None,
                           today: date | None = None) -> list[FindingResult]:
    p = policies or DEFAULTS
    today = today or date.today()
    retention = p["snapshot_retention_days"]
    findings = []
    for r in resources:
        if r.resource_type != "snapshot" or r.created_at is None:
            continue
        age_days = (today - r.created_at).days
        if age_days <= retention:
            continue
        findings.append(FindingResult(
            resource=r, rule="old_snapshot", category="storage",
            severity=severity_for(r.monthly_cost, p),
            est_monthly_savings=round(r.monthly_cost, 2),
            reason=f"Snapshot is {age_days} days old (> {retention}-day retention) "
                   f"and costs ${r.monthly_cost:.2f}/mo.",
        ))
    return findings
