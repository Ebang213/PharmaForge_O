resource "aws_elasticache_subnet_group" "this" {
  name       = "pharmaforge-${var.environment}"
  subnet_ids = var.subnet_ids

  tags = {
    Name        = "pharmaforge-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_security_group" "redis" {
  name_prefix = "pharmaforge-redis-${var.environment}-"
  vpc_id      = var.vpc_id
  description = "Security group for PharmaForge ElastiCache Redis"

  ingress {
    description     = "Redis from application"
    from_port       = 6379
    to_port         = 6379
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
    Name        = "pharmaforge-redis-${var.environment}"
    Environment = var.environment
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_elasticache_cluster" "this" {
  cluster_id           = "pharmaforge-${var.environment}"
  engine               = "redis"
  engine_version       = "7.0"
  node_type            = var.node_type
  num_cache_nodes      = var.num_cache_nodes
  parameter_group_name = "default.redis7"
  port                 = 6379

  subnet_group_name  = aws_elasticache_subnet_group.this.name
  security_group_ids = [aws_security_group.redis.id]

  tags = {
    Name        = "pharmaforge-${var.environment}"
    Environment = var.environment
  }
}
