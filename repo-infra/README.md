# AWS Infrastructure — Agentic AI System

Terraform configuration to deploy the full system to AWS using **ECS Fargate** + **Amazon Bedrock**.

## Architecture

```
Internet
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│  ALB (port 80 → 443 when ACM certificate is added)      │
│  POST /v1/chat/completions  (OpenAI-compatible)         │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  ECS Fargate — agentic-ai-api  (private subnet)         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  LangGraph workflow (deterministic control plane) │   │
│  │  Strands Financial Orchestrator (data plane)     │   │
│  │  MCP servers as subprocesses (stdio)             │   │
│  └─────────────────────────────────────────────────┘   │
└───────────────┬─────────────────────────────────────────┘
                │ IAM auth — no API keys needed
                ▼
         Amazon Bedrock
         (Claude Sonnet + Haiku)
```

## Terraform files

| File | Resources |
|------|-----------|
| `main.tf` | AWS + random providers, S3 backend (commented out, ready to activate) |
| `variables.tf` | All input variables with sensible defaults |
| `locals.tf` | Computed values: name_prefix, Bedrock model IDs, ECR image URI |
| `outputs.tf` | ALB DNS, ECR URL, cluster name, secret ARN, Aurora endpoint |
| `networking.tf` | VPC, 3 subnet tiers (public/private/isolated), NAT Gateway, security groups |
| `vpc_endpoints.tf` | VPC Endpoints: Bedrock, ECR×2, Secrets Manager, CloudWatch Logs, SQS + S3 gateway |
| `ecr.tf` | ECR repository with lifecycle policy (keep 5 tagged releases) |
| `iam.tf` | Task role (Bedrock + SQS + DynamoDB) + ECS Execution role |
| `data.tf` | Aurora Serverless v2 (pgvector), DynamoDB agent registry, SQS + DLQ, Secrets Manager |
| `ecs.tf` | ECS cluster, Fargate task definition, service, CloudWatch log group |
| `alb.tf` | Application Load Balancer, target group, HTTP listener (HTTPS stub commented out) |
| `autoscaling.tf` | Auto-scaling by CPU and memory utilization (1–4 tasks) |
| `terraform.tfvars.example` | Variable template — copy to `terraform.tfvars` before deploying |

## Prerequisites

```bash
# Terraform 1.5+
terraform --version

# AWS CLI configured
aws configure
aws sts get-caller-identity   # verify credentials

# Docker (for image build and push)
docker --version
```

## Step-by-step deployment

### 1. Set variables

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
```

### 2. (Optional) Configure remote state

```bash
# Create S3 bucket for state storage
aws s3 mb s3://my-tf-state-bucket --region us-east-1

# Create DynamoDB table for state locking
aws dynamodb create-table \
  --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1

# Uncomment the backend "s3" block in main.tf and fill in bucket/key/region
```

### 3. Init and plan

```bash
terraform init
terraform plan -out=tfplan
# Review the plan before applying
```

### 4. Create infrastructure (without image)

```bash
terraform apply tfplan
```

This provisions all resources. The ECS service will start with `image_tag=latest`
and fail its health check until a real image is pushed in the next step.

### 5. Build and push the Docker image

Run from the **project root** (not `infra/`):

```bash
# Get ECR URL from outputs
ECR_URL=$(terraform -chdir=infra output -raw ecr_api_repository_url)
IMAGE_TAG=$(git rev-parse --short HEAD)

# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin ${ECR_URL%/*}

# Build and push
docker build -t ${ECR_URL}:${IMAGE_TAG} .
docker tag  ${ECR_URL}:${IMAGE_TAG} ${ECR_URL}:latest
docker push ${ECR_URL}:${IMAGE_TAG}
docker push ${ECR_URL}:latest
```

### 6. Redeploy with the correct image tag

```bash
cd infra
TF_VAR_image_tag=${IMAGE_TAG} terraform apply -auto-approve
```

### 7. Populate secrets

```bash
SECRET_ARN=$(terraform output -raw app_secret_arn)

aws secretsmanager put-secret-value \
  --secret-id ${SECRET_ARN} \
  --secret-string '{
    "ANTHROPIC_API_KEY": "sk-ant-XXXXXX",
    "BRAVE_API_KEY": "BSA-XXXXXX",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-XXXXXX",
    "LANGFUSE_SECRET_KEY": "sk-lf-XXXXXX"
  }'
```

### 8. Force ECS redeployment to pick up the new secrets

```bash
CLUSTER=$(terraform output -raw ecs_cluster_name)
SERVICE=$(terraform output -raw ecs_service_name)

aws ecs update-service \
  --cluster ${CLUSTER} \
  --service ${SERVICE} \
  --force-new-deployment
```

### 9. Verify

```bash
ALB=$(terraform output -raw alb_dns_name)

# Health check
curl -s http://${ALB}/

# Test query
curl -s http://${ALB}/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Who are the top HY traders?"}]}'
```

## Enable pgvector on Aurora (one-time setup)

```bash
# Retrieve Aurora credentials
aws secretsmanager get-secret-value \
  --secret-id /agentic-ai-staging/aurora/credentials \
  --query SecretString --output text | jq .

# Connect and enable extension
psql -h $(terraform output -raw aurora_endpoint) \
     -U agenticai -d agenticai \
     -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

## Cost estimate (staging, 1 task running 24/7)

| Resource | $/month (approx) |
|----------|-----------------|
| ECS Fargate (1 vCPU, 2 GB) | ~$30 |
| ALB | ~$20 |
| NAT Gateway | ~$35 |
| VPC Interface Endpoints (6) | ~$50 |
| Aurora Serverless v2 (0.5 ACU, auto-pauses) | ~$5–15 |
| CloudWatch Logs | ~$2 |
| **Total** | **~$140–155** |

> To reduce costs in staging: comment out the VPC endpoints in `vpc_endpoints.tf`
> (traffic will go through NAT instead — ~$35/month extra but no fixed endpoint cost),
> set `desired_count = 0` when not in use, and allow Aurora auto-pause.

## Destroy infrastructure

```bash
# WARNING: destroys everything including the database
terraform destroy

# If Aurora has deletion_protection=true, disable it first:
terraform apply -var="aurora_deletion_protection=false"
terraform destroy
```

## CI/CD (GitHub Actions)

```yaml
# .github/workflows/deploy.yml
name: Deploy to AWS
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write   # OIDC auth
      contents: read

    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::ACCOUNT_ID:role/github-actions-deploy
          aws-region: us-east-1

      - name: Login to ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push Docker image
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $ECR_REGISTRY/agentic-ai-staging-api:$IMAGE_TAG .
          docker push $ECR_REGISTRY/agentic-ai-staging-api:$IMAGE_TAG

      - name: Terraform deploy
        working-directory: infra
        env:
          TF_VAR_image_tag: ${{ github.sha }}
        run: |
          terraform init
          terraform apply -auto-approve
```

## Phase 2 — Multi-tenant agent platform

See `prompts/replication_guide.md` section 7 for the full architecture.

Key changes needed:
1. Extract each Strands agent to its own ECS service
2. Switch MCP clients from `stdio` to `http+sse` transport
3. Add an SQS consumer per agent service for async job dispatch
4. Use the DynamoDB Agent Registry for dynamic agent discovery
