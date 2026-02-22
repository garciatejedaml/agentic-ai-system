# AWS CDK Infrastructure — Agentic AI System

Deploys the full agentic AI system to AWS using **ECS Fargate** + **Amazon Bedrock**.

## Architecture

```
Internet
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│  ALB (port 80 → HTTPS 443 when cert added)              │
│  POST /v1/chat/completions  (OpenAI-compatible)         │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  ECS Fargate — agentic-ai-api  (private subnet)         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  LangGraph workflow (deterministic control plane) │   │
│  │   ├─ intake → retrieve → strands → format        │   │
│  │   └─ Strands orchestrator (non-deterministic)    │   │
│  │       ├─ Financial Orchestrator (Sonnet via BR)  │   │
│  │       │   ├─ KDB Agent (Haiku via Bedrock)       │   │
│  │       │   └─ AMPS Agent (Haiku via Bedrock)      │   │
│  │       └─ General Researcher + Synthesizer        │   │
│  │  MCP servers as subprocesses (stdio)             │   │
│  │   ├─ kdb_mcp_server.py  (DuckDB/parquet)         │   │
│  │   └─ amps_mcp_server.py (disabled by default)    │   │
│  └─────────────────────────────────────────────────┘   │
└───────────────┬─────────────────────────────────────────┘
                │
        ┌───────┴──────────┐
        ▼                  ▼
  Amazon Bedrock      ChromaDB (in-process)
  (Claude models)     or Aurora pgvector (opt)
        │
  IAM auth only
  (no API keys)
```

## Stacks

| Stack | Purpose |
|-------|---------|
| `*-Network` | VPC, subnets, security groups, VPC endpoints |
| `*-ECR` | ECR repositories (image registry) |
| `*-Data` | Aurora Serverless v2, DynamoDB, SQS, Secrets Manager |
| `*-IAM` | ECS task roles with Bedrock + SQS + DynamoDB permissions |
| `*-ECS` | ECS cluster, Fargate service, ALB, auto-scaling |

## Prerequisites

1. **AWS CLI configured**: `aws configure` with an account that has admin access
2. **Node.js 18+**: required by CDK CLI
3. **CDK CLI**: `npm install -g aws-cdk`
4. **Python CDK deps**:
   ```bash
   cd infra
   python -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

## Build the Docker image

From the **project root** (not `infra/`):

```bash
# Set your AWS account and region
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_DEFAULT_REGION=us-east-1

# Log into ECR
aws ecr get-login-password | docker login \
  --username AWS \
  --password-stdin \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com

# Build and push (run after deploying ECR stack)
IMAGE_TAG=$(git rev-parse --short HEAD)
IMAGE_URI=${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/agentic-ai-api:${IMAGE_TAG}

docker build -t ${IMAGE_URI} .
docker push ${IMAGE_URI}
```

## Deploy

```bash
cd infra
export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export CDK_DEFAULT_REGION=us-east-1
export APP_ENV=staging

# First time: bootstrap CDK in your account/region
cdk bootstrap aws://${CDK_DEFAULT_ACCOUNT}/${CDK_DEFAULT_REGION}

# Deploy all stacks
cdk deploy --all

# Or step by step (recommended first time):
cdk deploy AgenticAI-Staging-Network
cdk deploy AgenticAI-Staging-ECR
# Build and push image here (see above)
cdk deploy AgenticAI-Staging-Data
cdk deploy AgenticAI-Staging-IAM
CDK_IMAGE_TAG=${IMAGE_TAG} cdk deploy AgenticAI-Staging-ECS
```

## Set secrets after first deploy

The Secrets Manager secret is created with placeholder values. Replace them:

```bash
aws secretsmanager put-secret-value \
  --secret-id /agenticai/app/secrets \
  --secret-string '{
    "ANTHROPIC_API_KEY": "sk-ant-XXXXXX",
    "BRAVE_API_KEY": "BSA_XXXXXX",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-XXXXXX",
    "LANGFUSE_SECRET_KEY": "sk-lf-XXXXXX"
  }'
```

After setting secrets, force a new ECS deployment to pick them up:
```bash
aws ecs update-service \
  --cluster agentic-ai \
  --service agentic-ai-api \
  --force-new-deployment
```

## Test the deployment

```bash
# Get the ALB DNS name from the CDK output or:
ALB=$(aws cloudformation describe-stacks \
  --stack-name AgenticAI-Staging-ECS \
  --query "Stacks[0].Outputs[?OutputKey=='AlbDnsName'].OutputValue" \
  --output text)

curl -s http://${ALB}/

curl -s http://${ALB}/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"What bond desks are available?"}]}'
```

## Cost estimate (staging, 1 task)

| Resource | $/month (approx) |
|----------|-----------------|
| ECS Fargate (1 vCPU, 2 GB, 24/7) | ~$30 |
| ALB | ~$20 |
| NAT Gateway | ~$35 |
| Aurora Serverless v2 (0.5 ACU, auto-pauses) | ~$5–15 |
| VPC Endpoints (7) | ~$50 |
| CloudWatch Logs | ~$2 |
| **Total** | **~$140–160** |

> To minimize cost in staging: remove VPC endpoints (use NAT instead), set
> `desired_count=0` when not testing, enable Aurora auto-pause.

## CI/CD (GitHub Actions sketch)

```yaml
# .github/workflows/deploy.yml
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::ACCOUNT::role/github-actions-deploy
          aws-region: us-east-1
      - run: docker build -t $IMAGE_URI .
      - run: docker push $IMAGE_URI
      - run: cd infra && CDK_IMAGE_TAG=${{ github.sha }} cdk deploy --all --require-approval never
```

## Extending to multi-tenant platform (V2)

See `prompts/replication_guide.md` — "Phase 2: Multi-tenant Agent Platform" section.

Key changes:
1. Extract each Strands agent to its own ECS service (separate Fargate service per agent type)
2. Switch MCP clients from `stdio` to `http+sse` transport
3. Add SQS consumer in each agent service to pick up async jobs
4. Use the DynamoDB Agent Registry for dynamic agent discovery
5. Expose agent endpoints via API Gateway for external team onboarding
