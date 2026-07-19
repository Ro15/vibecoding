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
