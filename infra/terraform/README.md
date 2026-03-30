# PharmaForge OS — Terraform Infrastructure

Infrastructure as Code for deploying PharmaForge OS to AWS using ECS Fargate.

> **This is entirely optional.** The local Docker workflow (`docker compose up`) continues to work without any changes.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                        VPC                          │
│                                                     │
│  ┌─── Public Subnets ───┐  ┌── Private Subnets ──┐ │
│  │                       │  │                      │ │
│  │   ALB (port 80/443)   │  │   ECS Fargate Tasks  │ │
│  │   NAT Gateway         │  │   RDS PostgreSQL 15  │ │
│  │   Internet Gateway    │  │   ElastiCache Redis 7 │ │
│  │                       │  │                      │ │
│  └───────────────────────┘  └──────────────────────┘ │
│                                                     │
│  ECR Repository (container images)                  │
│  CloudWatch Logs (container output)                 │
└─────────────────────────────────────────────────────┘
```

## Two Deployment Targets

| Target | How | When |
|--------|-----|------|
| **Local** | `docker compose up` | Development, testing |
| **AWS Cloud** | `terraform apply` in this directory | Staging, production |

## Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/downloads) >= 1.5
- AWS CLI configured with credentials (`aws configure`)
- Docker (for building and pushing images)

## Quick Start

### 1. Configure Variables

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
```

### 2. Set Secrets via Environment Variables

```bash
# Required
export TF_VAR_db_password="your-strong-database-password"
export TF_VAR_secret_key="your-minimum-32-character-secret-key-here"

# Optional (LLM provider keys)
export TF_VAR_openai_api_key="sk-..."
export TF_VAR_anthropic_api_key="sk-ant-..."
```

On Windows (PowerShell):

```powershell
$env:TF_VAR_db_password = "your-strong-database-password"
$env:TF_VAR_secret_key = "your-minimum-32-character-secret-key-here"
```

### 3. Deploy Infrastructure

```bash
terraform init
terraform plan        # Review changes
terraform apply       # Apply changes
```

### 4. Build and Push the Docker Image

After `terraform apply` completes, push your app image to ECR:

```bash
# Get the ECR repository URL from Terraform output
ECR_URL=$(terraform output -raw ecr_repository_url)
AWS_REGION=$(terraform output -raw aws_region 2>/dev/null || echo "us-east-1")

# Authenticate Docker with ECR
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_URL

# Build and push (from project root)
cd ../..
docker build -t $ECR_URL:latest .
docker push $ECR_URL:latest
```

### 5. Force New Deployment (after image push)

```bash
CLUSTER=$(terraform output -raw ecs_cluster_name)
SERVICE=$(terraform output -raw ecs_service_name)
aws ecs update-service --cluster $CLUSTER --service $SERVICE --force-new-deployment
```

## Modules

| Module | Resources | Purpose |
|--------|-----------|---------|
| `modules/database` | RDS PostgreSQL 15, Security Group, DB Subnet Group | Managed database |
| `modules/redis` | ElastiCache Redis 7, Security Group, Cache Subnet Group | Caching and job queues |
| `modules/app` | ECR, ECS Cluster/Service/Task, ALB, IAM Roles, CloudWatch Logs | Application runtime |

## Outputs

After `terraform apply`, these values are available:

```bash
terraform output alb_dns_name        # Application URL
terraform output ecr_repository_url  # Where to push images
terraform output db_endpoint         # RDS endpoint
terraform output redis_endpoint      # ElastiCache endpoint
```

## Shared State (Teams)

For team use, uncomment the S3 backend in `providers.tf` and create the state bucket:

```bash
aws s3api create-bucket --bucket pharmaforge-terraform-state --region us-east-1
aws dynamodb create-table \
  --table-name pharmaforge-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

## Teardown

```bash
terraform destroy
```

> **Warning:** In production (`environment = "production"`), the RDS instance has deletion protection enabled. Disable it in the AWS console before running `terraform destroy`.

## Security Notes

- All secrets are passed via `TF_VAR_*` environment variables, never stored in files
- RDS and Redis are in private subnets with no public access
- Only the ALB is publicly accessible
- ECS tasks run in private subnets behind a NAT gateway
- Security groups restrict traffic: ALB → ECS → RDS/Redis only
- ECR image scanning is enabled on push
- Container logs are retained for 30 days in CloudWatch
