# repo-infra — AWS Infrastructure

Terraform configuration to deploy the full Agentic AI System to AWS using
**ECS Fargate** + **Amazon Bedrock** + **AWS Cloud Map**.

## Architecture

```
Internet
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│  ALB (port 80 / 443)                                             │
│  POST /v1/chat/completions  (OpenAI-compatible)                  │
│  Header routing: X-Agent-Service → agent target group            │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  ECS Fargate — api-service (private subnet, port 8000)           │
│  LangGraph → LLM Router (Haiku) → A2A fan-out                   │
└──────┬──────────────────────────────────────────────────────────┘
       │  A2A HTTP  (Cloud Map DNS: {name_prefix}-{agent}.{env}.local)
       ├──► kdb-agent        :8001   KDB+ / S3 Parquet (6-month RFQ)
       ├──► amps-agent       :8002   AMPS Core (live SOW queries)
       ├──► portfolio-agent  :8004   AMPS portfolio_nav topic
       ├──► cds-agent        :8005   AMPS cds_spreads topic
       ├──► etf-agent        :8006   AMPS etf_nav topic
       └──► risk-pnl-agent   :8007   AMPS risk_metrics topic
                               │
                               ▼ IAM auth — no API keys
                        Amazon Bedrock
                   Claude Sonnet 4.6 (synthesis)
                   Claude Haiku 4.5  (routing)
```

## Prerequisites

Before running `terraform apply`:

1. **Enable Bedrock model access** in your AWS account and region:
   - Go to AWS Console → Amazon Bedrock → Model access
   - Request access for:
     - `Claude Sonnet 4.6` (Anthropic)
     - `Claude Haiku 4.5` (Anthropic)
   - Cross-region inference profiles are used (`us.anthropic.*`) — enable in `us-east-1`

2. **AWS CLI configured** with an IAM user/role that has permissions to create ECS, VPC, ALB, DynamoDB, IAM, ECR, and Cloud Map resources.

3. **Terraform ≥ 1.5** and **Docker** installed locally.

4. **Docker image built** — the ECR repository is created by Terraform, then you push the image (step 5 below).

---

## Terraform files

| File | Resources |
|------|-----------|
| `main.tf` | AWS provider, S3 backend (uncomment to activate) |
| `variables.tf` | All input variables with defaults |
| `locals.tf` | `name_prefix`, Bedrock model IDs, ECR image URI |
| `outputs.tf` | ALB DNS, ECR URL, cluster name, DynamoDB table names |
| `networking.tf` | VPC, 3 subnet tiers (public/private/isolated), NAT, security groups |
| `vpc_endpoints.tf` | Interface endpoints: Bedrock, ECR×2, Secrets Manager, CloudWatch, SQS + S3 gateway |
| `ecr.tf` | ECR repository (5 tagged releases kept) |
| `iam.tf` | Task role (Bedrock + DynamoDB + SQS + Secrets Manager), Execution role |
| `data.tf` | Aurora Serverless v2 (pgvector), DynamoDB tables (agent-registry, sessions, mcp-registry, token-usage), SQS + DLQ, Secrets Manager |
| `service_discovery.tf` | AWS Cloud Map private DNS namespace + service records for all 7 agents |
| `ecs.tf` | ECS cluster, Fargate task definitions + services for api + 7 agents, CloudWatch log groups |
| `alb.tf` | ALB, target groups, HTTP listener, `X-Agent-Service` header routing rules for all 7 agents |
| `autoscaling.tf` | CPU/memory-based auto-scaling (1–4 tasks per service) |

## Agent internal DNS (Cloud Map)

After `terraform apply`, each agent registers its IP with Cloud Map. DNS resolves within the VPC:

```
agentic-ai-staging-kdb-agent.staging.local       → container IP, port 8001
agentic-ai-staging-amps-agent.staging.local      → container IP, port 8002
agentic-ai-staging-portfolio-agent.staging.local → container IP, port 8004
agentic-ai-staging-cds-agent.staging.local       → container IP, port 8005
agentic-ai-staging-etf-agent.staging.local       → container IP, port 8006
agentic-ai-staging-risk-pnl-agent.staging.local  → container IP, port 8007
```

## Step-by-step deployment

### 1. Set variables

```bash
cd repo-infra
cp terraform.tfvars.example terraform.tfvars
# Required: aws_region, environment, image_tag
# Optional: amps_host, langfuse_host (internal URL of self-hosted Langfuse)
```

### 2. Configure remote state (recommended)

```bash
aws s3 mb s3://my-tf-state-bucket --region us-east-1
aws dynamodb create-table \
  --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
# Uncomment the backend "s3" block in main.tf
```

### 3. Init and plan

```bash
terraform init
terraform plan -out=tfplan
```

### 4. Apply infrastructure

```bash
terraform apply tfplan
# ECS services will be unhealthy until the Docker image is pushed (next step)
```

### 5. Build and push Docker image

From the **repo root**:

```bash
ECR_URL=$(terraform -chdir=repo-infra output -raw ecr_api_repository_url)
IMAGE_TAG=$(git rev-parse --short HEAD)

aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin ${ECR_URL%/*}

docker build -f repo-api/Dockerfile -t ${ECR_URL}:${IMAGE_TAG} .
docker tag  ${ECR_URL}:${IMAGE_TAG} ${ECR_URL}:latest
docker push ${ECR_URL}:${IMAGE_TAG}
docker push ${ECR_URL}:latest
```

### 6. Redeploy with the correct image tag

```bash
cd repo-infra
TF_VAR_image_tag=${IMAGE_TAG} terraform apply -auto-approve
```

### 7. Populate secrets

```bash
SECRET_ARN=$(terraform output -raw app_secret_arn)

aws secretsmanager put-secret-value \
  --secret-id ${SECRET_ARN} \
  --secret-string '{
    "BRAVE_API_KEY":        "BSA-XXXXXX",
    "LANGFUSE_PUBLIC_KEY":  "pk-lf-XXXXXX",
    "LANGFUSE_SECRET_KEY":  "sk-lf-XXXXXX",
    "DYNATRACE_API_TOKEN":  ""
  }'
```

> `ANTHROPIC_API_KEY` is **not** needed in AWS — Bedrock uses the ECS task IAM role.

### 8. Force redeployment to pick up secrets

```bash
CLUSTER=$(terraform output -raw ecs_cluster_name)

for SERVICE in api kdb-agent amps-agent portfolio-agent cds-agent etf-agent risk-pnl-agent; do
  aws ecs update-service \
    --cluster ${CLUSTER} \
    --service agentic-ai-staging-${SERVICE} \
    --force-new-deployment
done
```

### 9. Verify

```bash
ALB=$(terraform output -raw alb_dns_name)

# Health check
curl -s http://${ALB}/

# Test query (routed through LLM Router → agents)
curl -s http://${ALB}/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Who are the top HY traders by hit rate?"}]}' \
  | jq .choices[0].message.content

# Check agent logs
aws logs tail /agentic-ai/staging/kdb-agent --follow
aws logs tail /agentic-ai/staging/api        --follow
```

## Observability

Set `langfuse_host` in `terraform.tfvars` to the internal DNS of your self-hosted Langfuse:

```hcl
langfuse_host = "http://langfuse-web.staging.local:3000"
```

Or deploy Langfuse separately and provide its internal ALB URL.
The API task has `OBSERVABILITY_ENABLED=true` — it will trace to Langfuse automatically
once `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are in Secrets Manager.

## Cost estimate (staging — all 7 agents, 24/7)

| Resource | $/month (approx) |
|----------|-----------------|
| ECS Fargate — api (1 vCPU, 2 GB) | ~$30 |
| ECS Fargate — 6 agents (0.5 vCPU, 1 GB each) | ~$55 |
| ALB | ~$20 |
| NAT Gateway | ~$35 |
| VPC Interface Endpoints (6) | ~$50 |
| Aurora Serverless v2 (auto-pauses when idle) | ~$5–15 |
| AWS Cloud Map | ~$1 |
| CloudWatch Logs | ~$5 |
| **Total** | **~$200–215** |

> Cost tip: set `desired_count = 0` on agents not in use, and comment out VPC endpoints
> to replace with NAT routing (~$35/month cheaper at low traffic).

## Destroy

```bash
# WARNING: destroys everything including DynamoDB tables and Aurora
terraform destroy

# If Aurora has deletion_protection=true:
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
      id-token: write   # OIDC auth — no AWS keys in GitHub secrets
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

      - name: Build and push
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -f repo-api/Dockerfile \
            -t $ECR_REGISTRY/agentic-ai-staging-api:$IMAGE_TAG .
          docker push $ECR_REGISTRY/agentic-ai-staging-api:$IMAGE_TAG

      - name: Terraform apply
        working-directory: repo-infra
        env:
          TF_VAR_image_tag: ${{ github.sha }}
        run: |
          terraform init
          terraform apply -auto-approve
```
