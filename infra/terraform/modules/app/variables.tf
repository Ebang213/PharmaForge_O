variable "environment" {
  description = "Environment name (e.g. staging, production)"
  type        = string
}

variable "app_name" {
  description = "Application name used for resource naming"
  type        = string
  default     = "pharmaforge"
}

variable "vpc_id" {
  description = "VPC ID where the app will be deployed"
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for the ALB"
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for ECS tasks"
  type        = list(string)
}

variable "app_port" {
  description = "Port the application listens on"
  type        = number
  default     = 8000
}

variable "cpu" {
  description = "Fargate task CPU units (256 = 0.25 vCPU)"
  type        = number
  default     = 512
}

variable "memory" {
  description = "Fargate task memory in MB"
  type        = number
  default     = 1024
}

variable "desired_count" {
  description = "Number of ECS tasks to run"
  type        = number
  default     = 2
}

variable "health_check_path" {
  description = "Health check endpoint path"
  type        = string
  default     = "/api/health"
}

variable "environment_variables" {
  description = "Non-secret environment variables for the container"
  type        = map(string)
  default     = {}
}

variable "secrets" {
  description = "Map of secret name to SSM Parameter ARN for sensitive env vars"
  type        = map(string)
  default     = {}
}
