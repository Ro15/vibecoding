"""Rule: snapshots older than the retention threshold."""
from __future__ import annotations

from datetime import date

from app.core.models import FindingResult, NormalizedResource
from app.core.registry import rule, severity_for

RETENTION_DAYS = 90


@rule("old_snapshot", category="storage")
def evaluate_old_snapshots(resources: list[NormalizedResource],
                           today: date | None = None) -> list[FindingResult]:
    today = today or date.today()
    findings = []
    for r in resources:
        if r.resource_type != "snapshot" or r.created_at is None:
            continue
        age_days = (today - r.created_at).days
        if age_days <= RETENTION_DAYS:
            continue
        findings.append(FindingResult(
            resource=r,
            rule="old_snapshot",
            category="storage",
            severity=severity_for(r.monthly_cost),
            est_monthly_savings=round(r.monthly_cost, 2),
            reason=f"Snapshot is {age_days} days old (> {RETENTION_DAYS}-day retention) "
                   f"and costs ${r.monthly_cost:.2f}/mo.",
        ))
    return findings
