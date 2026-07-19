"""Security-group ingress policies."""
from __future__ import annotations

from apps.guardrail.core.models import Finding
from apps.guardrail.core.registry import policy

OPEN_CIDRS = {"0.0.0.0/0", "::/0"}


def _port_covered(rule: dict, port: int) -> bool:
    lo, hi = rule.get("from_port"), rule.get("to_port")
    if lo is None or hi is None:
        return False
    try:
        return int(lo) <= port <= int(hi)
    except (TypeError, ValueError):
        return False


def _world_open(rule: dict) -> bool:
    return rule.get("cidr") in OPEN_CIDRS


@policy("sg_open_ssh", severity="high", framework="CIS 5.2", rtypes=["security_group"])
def sg_open_ssh(resources):
    out = []
    for r in resources:
        for rule in r.config.get("ingress", []):
            if _world_open(rule) and _port_covered(rule, 22):
                out.append(Finding(
                    resource=r, policy="sg_open_ssh", title="SSH open to the world",
                    severity="high", framework="CIS 5.2",
                    detail=f"Security group '{r.name}' allows port 22 from {rule['cidr']}.",
                    remediation="Restrict the SSH ingress CIDR to your admin network/VPN."))
                break
    return out


@policy("sg_open_rdp", severity="high", framework="CIS 5.2", rtypes=["security_group"])
def sg_open_rdp(resources):
    out = []
    for r in resources:
        for rule in r.config.get("ingress", []):
            if _world_open(rule) and _port_covered(rule, 3389):
                out.append(Finding(
                    resource=r, policy="sg_open_rdp", title="RDP open to the world",
                    severity="high", framework="CIS 5.2",
                    detail=f"Security group '{r.name}' allows port 3389 from {rule['cidr']}.",
                    remediation="Restrict the RDP ingress CIDR to your admin network/VPN."))
                break
    return out


@policy("sg_open_all_ports", severity="critical", framework="CIS 5.3",
        rtypes=["security_group"])
def sg_open_all_ports(resources):
    out = []
    for r in resources:
        for rule in r.config.get("ingress", []):
            lo, hi = rule.get("from_port"), rule.get("to_port")
            if _world_open(rule) and lo in (0, "0") and hi in (65535, "65535"):
                out.append(Finding(
                    resource=r, policy="sg_open_all_ports",
                    title="All ports open to the world", severity="critical",
                    framework="CIS 5.3",
                    detail=f"Security group '{r.name}' allows ALL ports from {rule['cidr']}.",
                    remediation="Remove the 0-65535/0.0.0.0/0 rule; open only required ports."))
                break
    return out
