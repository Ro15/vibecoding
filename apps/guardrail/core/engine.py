"""Policy engine: type-indexed dispatch of every registered policy."""
from __future__ import annotations

from collections import defaultdict

# Importing these packages registers all parsers + policies.
from apps.guardrail.core import parsers, policies  # noqa: F401
from apps.guardrail.core.models import Finding, IacResource
from apps.guardrail.core.registry import all_policies


def run_policies(resources: list[IacResource]) -> list[Finding]:
    """Evaluate each policy only against resources of the types it declares.

    Total work is O(R + M): R resources bucketed once, then each policy sees only
    its relevant bucket — never the naive rules x resources product.
    """
    by_type: dict[str, list] = defaultdict(list)
    for r in resources:
        by_type[r.rtype].append(r)

    findings: list[Finding] = []
    for entry in all_policies().values():
        relevant = [res for t in entry.rtypes for res in by_type.get(t, [])]
        if relevant:
            findings.extend(entry.evaluate(relevant))
    # stable severity ordering for display
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda f: order.get(f.severity, 9))
    return findings
