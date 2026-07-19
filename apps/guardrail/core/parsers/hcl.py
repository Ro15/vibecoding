"""Terraform HCL parser (.tf) via python-hcl2.

hcl2 8.x emits string tokens wrapped in literal quotes and marks blocks with
`__is_block__`; we clean both recursively before extracting resources.
"""
from __future__ import annotations

import io
import json

import hcl2

from apps.guardrail.core.models import IacResource, classify
from apps.guardrail.core.parsers.common import _as_list, canonical_config
from apps.guardrail.core.registry import parser


def _unquote(s):
    if isinstance(s, str) and len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def _clean(v):
    if isinstance(v, dict):
        return {_unquote(k): _clean(val) for k, val in v.items() if k != "__is_block__"}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return _unquote(v)


def _ingress_rules(attrs: dict) -> list[dict]:
    rules = []
    for block in _as_list(attrs.get("ingress")):
        if not isinstance(block, dict):
            continue
        cidrs = _as_list(block.get("cidr_blocks")) or [None]
        for cidr in cidrs:
            rules.append({"from_port": block.get("from_port"),
                          "to_port": block.get("to_port"),
                          "cidr": cidr, "protocol": block.get("protocol")})
    return rules


def _strip_heredoc(s: str) -> str:
    """Turn a `<<MARKER\\n...body...\\nMARKER` heredoc into just its body."""
    if isinstance(s, str) and s.startswith("<<"):
        lines = s.split("\n")
        if len(lines) >= 3:
            return "\n".join(lines[1:-1])
    return s


def _iam_statements(attrs: dict) -> list[dict]:
    pol = _strip_heredoc(attrs.get("policy"))
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


@parser("hcl")
def parse_hcl(file_bytes: bytes, filename: str = "main.tf"):
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not valid UTF-8 text: {exc}") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # hcl2 lexer needs LF
    try:
        raw = hcl2.load(io.StringIO(text))
    except Exception as exc:  # hcl2 raises assorted lark errors
        raise ValueError(f"invalid Terraform HCL: {exc}") from exc

    resources: list[IacResource] = []
    errors: list[dict] = []
    for i, block in enumerate(_clean(raw).get("resource", []), start=1):
        if not isinstance(block, dict) or not block:
            errors.append({"line": i, "reason": "malformed resource block"})
            continue
        raw_type = next(iter(block))
        body = block[raw_type]
        if not isinstance(body, dict) or not body:
            errors.append({"line": i, "reason": f"malformed body for {raw_type}"})
            continue
        name = next(iter(body))
        attrs = body[name] if isinstance(body[name], dict) else {}
        provider, rtype = classify(raw_type)
        cfg = canonical_config(rtype, attrs,
                               ingress=_ingress_rules(attrs),
                               statements=_iam_statements(attrs))
        resources.append(IacResource(
            address=f"{raw_type}.{name}", provider=provider, rtype=rtype,
            raw_type=raw_type, name=name, config=cfg,
            source=filename, source_format="hcl"))
    return resources, errors
