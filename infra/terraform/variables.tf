# --- General ---

variable "environment" {
  description = "Environment name (e.g. staging, production)"
  type        = string
  default     = "staging"
}

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

# --- Networking ---

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones to use"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

# --- Database ---

variable "db_password" {
  description = "Master password for the RDS PostgreSQL instance — set via TF_VAR_db_password"
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "Allocated storage in GB for RDS"
  type        = number
  default     = 20
}

# --- Redis ---

variable "redis_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t3.micro"
}

# --- App ---

variable "app_cpu" {
  description = "Fargate task CPU units (256 = 0.25 vCPU)"
  type        = number
  default     = 512
}

variable "app_memory" {
  description = "Fargate task memory in MB"
  type        = number
  default     = 1024
}

variable "app_desired_count" {
  description = "Number of ECS tasks to run"
  type        = number
  default     = 2
}

# --- Secrets (pass via TF_VAR_* environment variables) ---

variable "secret_key" {
  description = "Application SECRET_KEY (min 32 chars) — set via TF_VAR_secret_key"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key (optional) — set via TF_VAR_openai_api_key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "anthropic_api_key" {
  description = "Anthropic API key (optional) — set via TF_VAR_anthropic_api_key"
  type        = string
  sensitive   = true
  default     = ""
}
