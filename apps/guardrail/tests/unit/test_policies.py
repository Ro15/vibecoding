from apps.guardrail.core.models import IacResource
from apps.guardrail.core.policies.ebs import ebs_unencrypted
from apps.guardrail.core.policies.iam import iam_wildcard
from apps.guardrail.core.policies.rds import rds_public, rds_unencrypted
from apps.guardrail.core.policies.s3 import (s3_no_encryption, s3_no_versioning,
                                             s3_public_acl)
from apps.guardrail.core.policies.security_groups import (sg_open_all_ports,
                                                          sg_open_rdp, sg_open_ssh)


def r(rtype, **config):
    return IacResource(address="a.b", provider="aws", rtype=rtype, raw_type="aws_x",
                       name="b", config=config)


def test_s3_public_acl():
    assert len(s3_public_acl([r("s3_bucket", acl="public-read")])) == 1
    assert len(s3_public_acl([r("s3_bucket", acl="public-read-write")])) == 1
    assert s3_public_acl([r("s3_bucket", acl="private")]) == []
    assert s3_public_acl([r("s3_bucket")]) == []


def test_s3_encryption_and_versioning():
    assert len(s3_no_encryption([r("s3_bucket", encrypted=False)])) == 1
    assert s3_no_encryption([r("s3_bucket", encrypted=True)]) == []
    assert len(s3_no_versioning([r("s3_bucket", versioning=False)])) == 1
    assert s3_no_versioning([r("s3_bucket", versioning=True)]) == []


def test_sg_open_ssh_rdp():
    open22 = r("security_group", ingress=[{"from_port": 22, "to_port": 22, "cidr": "0.0.0.0/0"}])
    assert len(sg_open_ssh([open22])) == 1
    closed = r("security_group", ingress=[{"from_port": 22, "to_port": 22, "cidr": "10.0.0.0/8"}])
    assert sg_open_ssh([closed]) == []
    open3389 = r("security_group", ingress=[{"from_port": 3389, "to_port": 3389, "cidr": "0.0.0.0/0"}])
    assert len(sg_open_rdp([open3389])) == 1


def test_sg_port_range_coverage():
    # a wide range covering 22 counts as open ssh
    wide = r("security_group", ingress=[{"from_port": 0, "to_port": 65535, "cidr": "0.0.0.0/0"}])
    assert len(sg_open_ssh([wide])) == 1
    assert len(sg_open_all_ports([wide])) == 1
    narrow = r("security_group", ingress=[{"from_port": 80, "to_port": 443, "cidr": "0.0.0.0/0"}])
    assert sg_open_ssh([narrow]) == []
    assert sg_open_all_ports([narrow]) == []


def test_sg_only_one_finding_per_resource():
    twice = r("security_group", ingress=[
        {"from_port": 22, "to_port": 22, "cidr": "0.0.0.0/0"},
        {"from_port": 22, "to_port": 22, "cidr": "0.0.0.0/0"}])
    assert len(sg_open_ssh([twice])) == 1


def test_rds_and_ebs():
    assert len(rds_public([r("rds_instance", publicly_accessible=True)])) == 1
    assert rds_public([r("rds_instance", publicly_accessible=False)]) == []
    assert len(rds_unencrypted([r("rds_instance", encrypted=False)])) == 1
    assert len(ebs_unencrypted([r("ebs_volume", encrypted=False)])) == 1
    assert ebs_unencrypted([r("ebs_volume", encrypted=True)]) == []


def test_iam_wildcard():
    admin = r("iam_policy", statements=[{"effect": "Allow", "actions": ["*"], "resources": ["*"]}])
    assert len(iam_wildcard([admin])) == 1
    scoped = r("iam_policy", statements=[{"effect": "Allow", "actions": ["s3:GetObject"], "resources": ["arn:..."]}])
    assert iam_wildcard([scoped]) == []
    deny = r("iam_policy", statements=[{"effect": "Deny", "actions": ["*"], "resources": ["*"]}])
    assert iam_wildcard([deny]) == []
