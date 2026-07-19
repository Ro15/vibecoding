"""Shared canonical-config extraction used by all three IaC parsers.

Once each parser turns its native format into a plain attribute dict, these
helpers project that dict onto the canonical per-rtype config the policies read.
Keeping this in one place means the policies never see format-specific shapes.
"""
from __future__ import annotations


def _as_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "1")
    return None


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def canonical_config(rtype: str, attrs: dict, *, ingress=None, statements=None) -> dict:
    """Project native attributes onto the canonical config for `rtype`.

    `ingress` / `statements` let a parser pass already-extracted nested blocks
    (security-group rules, IAM statements) since those differ most across formats.
    """
    if rtype == "s3_bucket":
        cfg = {}
        if "acl" in attrs:
            cfg["acl"] = attrs["acl"]
        for key, src in (("encrypted", ("encrypted", "server_side_encryption")),
                         ("public_access_block", ("public_access_block",)),
                         ("versioning", ("versioning",))):
            for s in src:
                if s in attrs:
                    b = _as_bool(attrs[s])
                    if b is not None:
                        cfg[key] = b
                    break
        return cfg
    if rtype == "security_group":
        return {"ingress": ingress or []}
    if rtype == "ec2_instance":
        cfg = {}
        if "associate_public_ip_address" in attrs:
            cfg["associate_public_ip"] = _as_bool(attrs["associate_public_ip_address"])
        return cfg
    if rtype == "rds_instance":
        cfg = {}
        if "publicly_accessible" in attrs:
            cfg["publicly_accessible"] = _as_bool(attrs["publicly_accessible"])
        if "storage_encrypted" in attrs:
            cfg["encrypted"] = _as_bool(attrs["storage_encrypted"])
        return cfg
    if rtype == "ebs_volume":
        cfg = {}
        if "encrypted" in attrs:
            cfg["encrypted"] = _as_bool(attrs["encrypted"])
        return cfg
    if rtype == "iam_policy":
        return {"statements": statements or []}
    return dict(attrs)


def normalize_ingress(rule: dict) -> dict:
    """Canonical ingress rule: {from_port, to_port, cidr, protocol}. cidr may be a list."""
    return {
        "from_port": rule.get("from_port"),
        "to_port": rule.get("to_port"),
        "cidr": rule.get("cidr"),
        "protocol": rule.get("protocol"),
    }
