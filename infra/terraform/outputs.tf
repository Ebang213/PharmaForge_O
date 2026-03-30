# --- App ---

output "alb_dns_name" {
  description = "Public DNS name of the Application Load Balancer"
  value       = module.app.alb_dns_name
}

output "ecr_repository_url" {
  description = "ECR repository URL — push images here"
  value       = module.app.ecr_repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = module.app.ecs_cluster_name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = module.app.ecs_service_name
}

# --- Database ---

output "db_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.database.db_endpoint
}

# --- Redis ---

output "redis_endpoint" {
  description = "ElastiCache Redis endpoint"
  value       = module.redis.redis_endpoint
}

# --- Networking ---

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.this.id
}
