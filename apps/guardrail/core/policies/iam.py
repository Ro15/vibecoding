"""IAM policy checks."""
from __future__ import annotations

from apps.guardrail.core.models import Finding
from apps.guardrail.core.registry import policy


@policy("iam_wildcard", severity="high", framework="CIS 1.16", rtypes=["iam_policy"])
def iam_wildcard(resources):
    out = []
    for r in resources:
        for st in r.config.get("statements", []):
            if str(st.get("effect")).lower() != "allow":
                continue
            actions = [str(a) for a in st.get("actions", [])]
            res = [str(x) for x in st.get("resources", [])]
            if "*" in actions and "*" in res:
                out.append(Finding(
                    resource=r, policy="iam_wildcard",
                    title="IAM policy grants *:* (full admin)", severity="high",
                    framework="CIS 1.16",
                    detail=f"Policy '{r.name}' allows all actions on all resources.",
                    remediation="Scope Action and Resource to the minimum required (least privilege)."))
                break
    return out
