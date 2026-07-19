"""Rules engine: runs every registered rule over normalized resources."""
from __future__ import annotations

from datetime import date

# Importing rule modules registers them via the @rule decorator.
from apps.costopt.core.rules import (aged_stopped_vms, idle_load_balancers, idle_vms,  # noqa: F401
                            old_snapshots, orphaned_ips, oversized_vms,
                            unattached_disks, untagged_resources,
                            unused_nat_gateways)
from apps.costopt.core.models import FindingResult, NormalizedResource
from apps.costopt.core.policies import DEFAULTS
from apps.costopt.core.registry import all_rules


def run_rules(resources: list[NormalizedResource], today: date | None = None,
              policies: dict | None = None) -> list[FindingResult]:
    today = today or date.today()
    policies = policies or dict(DEFAULTS)
    findings: list[FindingResult] = []
    for entry in all_rules().values():
        findings.extend(entry.evaluate(resources, policies=policies, today=today))
    return findings
