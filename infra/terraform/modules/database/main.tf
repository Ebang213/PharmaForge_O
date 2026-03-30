resource "aws_db_subnet_group" "this" {
  name       = "pharmaforge-${var.environment}"
  subnet_ids = var.subnet_ids

  tags = {
    Name        = "pharmaforge-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_security_group" "db" {
  name_prefix = "pharmaforge-db-${var.environment}-"
  vpc_id      = var.vpc_id
  description = "Security group for PharmaForge RDS"

  ingress {
    description     = "PostgreSQL from application"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = var.allowed_security_group_ids
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "pharmaforge-db-${var.environment}"
    Environment = var.environment
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_db_instance" "this" {
  identifier = "pharmaforge-${var.environment}"

  engine         = "postgres"
  engine_version = "15"
  instance_class = var.db_instance_class

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.allocated_storage * 2
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.db.id]
  multi_az               = var.multi_az
  publicly_accessible    = false

  backup_retention_period = 7
  skip_final_snapshot     = var.environment != "production"
  final_snapshot_identifier = var.environment == "production" ? "pharmaforge-${var.environment}-final" : null
  deletion_protection       = var.environment == "production"

  tags = {
    Name        = "pharmaforge-${var.environment}"
    Environment = var.environment
  }
}
