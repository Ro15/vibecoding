from pathlib import Path

import pytest

from apps.guardrail.core.parsers.cloudformation import parse_cloudformation
from apps.guardrail.core.parsers.hcl import parse_hcl
from apps.guardrail.core.parsers.tfplan import parse_tfplan

SD = Path(__file__).parents[2] / "sample_data"


def _load(name):
    return (SD / name).read_bytes()


def test_hcl_parses_all_resources():
    res, err = parse_hcl(_load("insecure.tf"), "insecure.tf")
    assert err == []
    by = {r.name: r for r in res}
    assert by["public_data"].rtype == "s3_bucket"
    assert by["public_data"].config["acl"] == "public-read"
    assert by["logs"].config["encrypted"] is False
    assert by["logs"].config["versioning"] is False
    assert by["prod"].rtype == "rds_instance"
    assert by["prod"].config["publicly_accessible"] is True
    assert by["data"].config["encrypted"] is False


def test_hcl_expands_ingress_cidrs_and_ports():
    res, _ = parse_hcl(_load("insecure.tf"), "insecure.tf")
    web = next(r for r in res if r.name == "web")
    ports = {(r["from_port"], r["cidr"]) for r in web.config["ingress"]}
    assert (22, "0.0.0.0/0") in ports
    assert (3389, "0.0.0.0/0") in ports
    assert (443, "10.0.0.0/8") in ports


def test_hcl_iam_policy_statements():
    res, _ = parse_hcl(_load("insecure.tf"), "insecure.tf")
    admin = next(r for r in res if r.rtype == "iam_policy")
    st = admin.config["statements"][0]
    assert st["effect"] == "Allow"
    assert st["actions"] == ["*"] and st["resources"] == ["*"]


def test_hcl_handles_crlf_and_bad_input():
    res, _ = parse_hcl(b'resource "aws_ebs_volume" "v" {\r\n  encrypted = false\r\n}\r\n', "x.tf")
    assert res[0].config["encrypted"] is False
    with pytest.raises(ValueError):
        parse_hcl(b'resource "aws_s3_bucket" {', "bad.tf")


def test_cfn_parses_yaml():
    res, err = parse_cloudformation(_load("insecure_cfn.yaml"), "insecure_cfn.yaml")
    assert err == []
    by = {r.name: r for r in res}
    assert by["PublicBucket"].config["acl"] == "public-read"
    assert by["ProdDatabase"].config["publicly_accessible"] is True
    assert by["ProdDatabase"].config["encrypted"] is False
    sg = by["WebSecurityGroup"].config["ingress"][0]
    assert sg["cidr"] == "0.0.0.0/0" and sg["from_port"] == 22


def test_cfn_rejects_non_template():
    with pytest.raises(ValueError):
        parse_cloudformation(b"just: some: yaml", "x.yaml")


def test_cfn_tolerates_intrinsics():
    tpl = b"""
Resources:
  B:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Ref SomeParam
      AccessControl: PublicRead
"""
    res, err = parse_cloudformation(tpl, "t.yaml")
    assert err == [] and res[0].config["acl"] == "public-read"


def test_tfplan_walks_child_modules():
    res, err = parse_tfplan(_load("plan.json"), "plan.json")
    assert err == []
    names = {r.name for r in res}
    assert names == {"public", "db", "open"}  # incl. one from a child module
    open_sg = next(r for r in res if r.name == "open")
    assert open_sg.config["ingress"][0]["cidr"] == "0.0.0.0/0"


def test_tfplan_rejects_non_plan():
    with pytest.raises(ValueError):
        parse_tfplan(b'{"foo": 1}', "x.json")


def test_secure_tf_is_clean():
    res, err = parse_hcl(_load("secure.tf"), "secure.tf")
    assert err == []
    assert all(r.rtype != "other" for r in res)
