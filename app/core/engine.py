"""Rules engine: runs every registered rule over normalized resources."""
from __future__ import annotations

import inspect
from datetime import date

# Importing rule modules registers them via the @rule decorator.
from app.core.rules import idle_vms, old_snapshots, orphaned_ips, unattached_disks  # noqa: F401
from app.core.models import FindingResult, NormalizedResource
from app.core.registry import all_rules


def run_rules(resources: list[NormalizedResource], today: date | None = None) -> list[FindingResult]:
    today = today or date.today()
    findings: list[FindingResult] = []
    for entry in all_rules().values():
        # Rules that care about "now" (e.g. snapshot age) accept an injected date.
        if "today" in inspect.signature(entry.evaluate).parameters:
            findings.extend(entry.evaluate(resources, today=today))
        else:
            findings.extend(entry.evaluate(resources))
    return findings
