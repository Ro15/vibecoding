"""CloudFormation parser (YAML or JSON)."""
from __future__ import annotations

import yaml

from apps.guardrail.core.models import IacResource, classify
from apps.guardrail.core.parsers.common import _as_list, canonical_config
from apps.guardrail.core.registry import parser


class _LaxLoader(yaml.SafeLoader):
    """Tolerate CloudFormation short-form intrinsics (!Ref, !GetAtt, …)."""


def _intrinsic(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


_LaxLoader.add_multi_constructor("!", _intrinsic)


def _sg_ingress(props: dict) -> list[dict]:
    rules = []
    for block in _as_list(props.get("SecurityGroupIngress")):
        if not isinstance(block, dict):
            continue
        cidr = block.get("CidrIp") or block.get("CidrIpv6")
        rules.append({"from_port": block.get("FromPort"),
                      "to_port": block.get("ToPort"),
                      "cidr": cidr, "protocol": block.get("IpProtocol")})
    return rules


def _iam_statements(props: dict) -> list[dict]:
    doc = props.get("PolicyDocument") or {}
    stmts = []
    for st in _as_list(doc.get("Statement", [])):
        if isinstance(st, dict):
            stmts.append({"effect": st.get("Effect"),
                          "actions": _as_list(st.get("Action", [])),
                          "resources": _as_list(st.get("Resource", []))})
    return stmts


def _s3_attrs(props: dict) -> dict:
    attrs = {}
    acl = props.get("AccessControl")
    if acl:
        # CFN uses PascalCase (PublicRead); normalize to terraform-style acl
        attrs["acl"] = {"PublicRead": "public-read",
                        "PublicReadWrite": "public-read-write",
                        "Private": "private"}.get(acl, str(acl).lower())
    if "BucketEncryption" in props:
        attrs["encrypted"] = bool(props.get("BucketEncryption"))
    if "VersioningConfiguration" in props:
        status = (props["VersioningConfiguration"] or {}).get("Status")
        attrs["versioning"] = (status == "Enabled")
    if "PublicAccessBlockConfiguration" in props:
        attrs["public_access_block"] = True
    return attrs


def parse_cfn_dict(doc: dict, filename: str):
    resources, errors = [], []
    for logical_id, res in (doc.get("Resources") or {}).items():
        if not isinstance(res, dict) or "Type" not in res:
            errors.append({"line": logical_id, "reason": "missing Type"})
            continue
        raw_type = res["Type"]
        props = res.get("Properties") or {}
        provider, rtype = classify(raw_type)
        if rtype == "s3_bucket":
            attrs = _s3_attrs(props)
        elif rtype == "rds_instance":
            attrs = {"publicly_accessible": props.get("PubliclyAccessible"),
                     "storage_encrypted": props.get("StorageEncrypted")}
        elif rtype == "ebs_volume":
            attrs = {"encrypted": props.get("Encrypted")}
        elif rtype == "ec2_instance":
            attrs = {}
        else:
            attrs = {}
        cfg = canonical_config(rtype, attrs,
                               ingress=_sg_ingress(props),
                               statements=_iam_statements(props))
        resources.append(IacResource(
            address=logical_id, provider=provider, rtype=rtype, raw_type=raw_type,
            name=logical_id, config=cfg, source=filename,
            source_format="cloudformation"))
    return resources, errors


@parser("cloudformation")
def parse_cloudformation(file_bytes: bytes, filename: str = "template.yaml"):
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file is not valid UTF-8 text: {exc}") from exc
    try:
        doc = yaml.load(text, Loader=_LaxLoader)  # YAML superset also loads JSON
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid CloudFormation template: {exc}") from exc
    if not isinstance(doc, dict) or "Resources" not in doc:
        raise ValueError("not a CloudFormation template: missing Resources section")
    return parse_cfn_dict(doc, filename)
