"""Sample IaC files with seeded misconfigurations (and one clean baseline).

Run: python apps/guardrail/sample_data/generate.py
Writes insecure.tf, insecure_cfn.yaml, plan.json, secure.tf.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent

INSECURE_TF = '''\
resource "aws_s3_bucket" "public_data" {
  bucket = "acme-public-data"
  acl    = "public-read"
}

resource "aws_s3_bucket" "logs" {
  bucket     = "acme-logs"
  encrypted  = false
  versioning = false
}

resource "aws_security_group" "web" {
  name = "web-sg"
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 3389
    to_port     = 3389
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }
}

resource "aws_security_group" "wide_open" {
  name = "wide-open-sg"
  ingress {
    from_port   = 0
    to_port     = 65535
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "prod" {
  publicly_accessible = true
  storage_encrypted   = false
}

resource "aws_ebs_volume" "data" {
  encrypted = false
}

resource "aws_iam_policy" "admin" {
  name   = "god-mode"
  policy = <<POLICY
{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]}
POLICY
}
'''

SECURE_TF = '''\
resource "aws_s3_bucket" "private_data" {
  bucket     = "acme-private-data"
  acl        = "private"
  encrypted  = true
  versioning = true
}

resource "aws_security_group" "admin" {
  name = "admin-sg"
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }
}

resource "aws_db_instance" "prod" {
  publicly_accessible = false
  storage_encrypted   = true
}

resource "aws_ebs_volume" "data" {
  encrypted = true
}
'''

INSECURE_CFN = '''\
AWSTemplateFormatVersion: "2010-09-09"
Resources:
  PublicBucket:
    Type: AWS::S3::Bucket
    Properties:
      AccessControl: PublicRead
  WebSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: web
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 22
          ToPort: 22
          CidrIp: 0.0.0.0/0
  ProdDatabase:
    Type: AWS::RDS::DBInstance
    Properties:
      PubliclyAccessible: true
      StorageEncrypted: false
  DataVolume:
    Type: AWS::EC2::Volume
    Properties:
      Encrypted: false
'''


def plan_json() -> dict:
    return {
        "format_version": "1.1",
        "terraform_version": "1.7.0",
        "planned_values": {
            "root_module": {
                "resources": [
                    {"address": "aws_s3_bucket.public", "type": "aws_s3_bucket",
                     "name": "public", "values": {"bucket": "planned-public",
                                                  "acl": "public-read"}},
                    {"address": "aws_db_instance.db", "type": "aws_db_instance",
                     "name": "db", "values": {"publicly_accessible": True,
                                              "storage_encrypted": False}},
                ],
                "child_modules": [
                    {"address": "module.net",
                     "resources": [
                         {"address": "module.net.aws_security_group.open",
                          "type": "aws_security_group", "name": "open",
                          "values": {"ingress": [{"from_port": 22, "to_port": 22,
                                                  "protocol": "tcp",
                                                  "cidr_blocks": ["0.0.0.0/0"]}]}},
                     ]},
                ],
            }
        },
    }


def main():
    (HERE / "insecure.tf").write_text(INSECURE_TF, encoding="utf-8")
    (HERE / "secure.tf").write_text(SECURE_TF, encoding="utf-8")
    (HERE / "insecure_cfn.yaml").write_text(INSECURE_CFN, encoding="utf-8")
    (HERE / "plan.json").write_text(json.dumps(plan_json(), indent=1), encoding="utf-8")
    print("wrote insecure.tf, secure.tf, insecure_cfn.yaml, plan.json")


if __name__ == "__main__":
    main()
