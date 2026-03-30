# =============================================================================
# VPC Networking
# =============================================================================

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "pharmaforge-${var.environment}"
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "pharmaforge-${var.environment}"
  }
}

# --- Public Subnets (ALB) ---

resource "aws_subnet" "public" {
  count                   = length(var.availability_zones)
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "pharmaforge-public-${var.availability_zones[count.index]}"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = {
    Name = "pharmaforge-public-${var.environment}"
  }
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# --- NAT Gateway (for private subnet egress) ---

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = {
    Name = "pharmaforge-nat-${var.environment}"
  }
}

resource "aws_nat_gateway" "this" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = {
    Name = "pharmaforge-${var.environment}"
  }

  depends_on = [aws_internet_gateway.this]
}

# --- Private Subnets (ECS, RDS, Redis) ---

resource "aws_subnet" "private" {
  count             = length(var.availability_zones)
  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 100)
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name = "pharmaforge-private-${var.availability_zones[count.index]}"
  }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this.id
  }

  tags = {
    Name = "pharmaforge-private-${var.environment}"
  }
}

resource "aws_route_table_association" "private" {
  count          = length(aws_subnet.private)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# =============================================================================
# Application Module (must be created first — its SG is referenced by DB/Redis)
# =============================================================================

module "app" {
  source = "./modules/app"

  environment        = var.environment
  vpc_id             = aws_vpc.this.id
  public_subnet_ids  = aws_subnet.public[*].id
  private_subnet_ids = aws_subnet.private[*].id
  cpu                = var.app_cpu
  memory             = var.app_memory
  desired_count      = var.app_desired_count

  environment_variables = {
    APP_NAME     = "PharmaForge OS"
    DEBUG        = "false"
    DATABASE_URL = module.database.db_connection_url
    REDIS_URL    = module.redis.redis_connection_url
    SECRET_KEY   = var.secret_key
    LLM_PROVIDER = var.openai_api_key != "" ? "openai" : "mock"
  }

  secrets = {}
}

# =============================================================================
# Database Module
# =============================================================================

module "database" {
  source = "./modules/database"

  environment                = var.environment
  vpc_id                     = aws_vpc.this.id
  subnet_ids                 = aws_subnet.private[*].id
  allowed_security_group_ids = [module.app.ecs_security_group_id]
  db_password                = var.db_password
  db_instance_class          = var.db_instance_class
  allocated_storage          = var.db_allocated_storage
  multi_az                   = var.environment == "production"
}

# =============================================================================
# Redis Module
# =============================================================================

module "redis" {
  source = "./modules/redis"

  environment                = var.environment
  vpc_id                     = aws_vpc.this.id
  subnet_ids                 = aws_subnet.private[*].id
  allowed_security_group_ids = [module.app.ecs_security_group_id]
  node_type                  = var.redis_node_type
}
