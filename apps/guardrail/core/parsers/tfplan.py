"""Terraform plan JSON parser (`terraform show -json`).

Reads planned_values.root_module.resources[] (and nested child_modules), where
each resource carries fully-resolved `values` — the most accurate input form.
"""
from __future__ import annotations

import json

from apps.guardrail.core.models import IacResource, classify
from apps.guardrail.core.parsers.common import _as_list, canonical_config
from apps.guardrail.core.registry import parser


def _walk_modules(module: dict):
    for res in module.get("resources", []):
        yield res
    for child in module.get("child_modules", []):
        yield from _walk_modules(child)


def _sg_ingress(values: dict) -> list[dict]:
    rules = []
    for block in _as_list(values.get("ingress")):
        if not isinstance(block, dict):
            continue
        cidrs = _as_list(block.get("cidr_blocks")) or [None]
        for cidr in cidrs:
            rules.append({"from_port": block.get("from_port"),
                          "to_port": block.get("to_port"),
                          "cidr": cidr, "protocol": block.get("protocol")})
    return rules


def _iam_statements(values: dict) -> list[dict]:
    pol = values.get("policy")
    stmts = []
    if isinstance(pol, str):
        try:
            doc = json.loads(pol)
        except (json.JSONDecodeError, TypeError):
            return stmts
        for st in _as_list(doc.get("Statement", [])):
            if isinstance(st, dict):
                stmts.append({"effect": st.get("Effect"),
                              "actions": _as_list(st.get("Action", [])),
                              "resources": _as_list(st.get("Resource", []))})
    return stmts


@parser("tfplan")
def parse_tfplan(file_bytes: bytes, filename: str = "plan.json"):
    try:
        doc = json.loads(file_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid terraform plan JSON: {exc}") from exc
    root = (doc.get("planned_values") or {}).get("root_module")
    if root is None:
        raise ValueError("not a terraform plan: missing planned_values.root_module")

    resources, errors = [], []
    for res in _walk_modules(root):
        raw_type = res.get("type")
        name = res.get("name", "")
        if not raw_type:
            errors.append({"line": res.get("address", "?"), "reason": "missing type"})
            continue
        values = res.get("values") or {}
        provider, rtype = classify(raw_type)
        cfg = canonical_config(rtype, values,
                               ingress=_sg_ingress(values),
                               statements=_iam_statements(values))
        resources.append(IacResource(
            address=res.get("address", f"{raw_type}.{name}"), provider=provider,
            rtype=rtype, raw_type=raw_type, name=name, config=cfg,
            source=filename, source_format="tfplan"))
    return resources, errors
