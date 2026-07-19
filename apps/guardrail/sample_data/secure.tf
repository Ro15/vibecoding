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
