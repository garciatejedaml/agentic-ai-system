# Agentic AI System

A production-grade multi-agent platform for fixed income trading desks. Traders submit natural language queries; the system routes them in parallel to specialist agents, synthesizes the results with per-data-point confidence scores, and returns a structured answer.

Built with **LangGraph**, **AWS Bedrock (Claude)**, **Strands Agents**, **AMPS real-time messaging**, and **OpenSearch RAG**. Runs locally with Docker Compose and deploys to AWS ECS Fargate with a single Terraform apply.

---

## Architecture

```
User Query  (POST /v1/chat/completions — OpenAI-compatible)
      │
      ▼
┌───────────────────────────────────────────────────────────────────┐
│  api-service :8000   FastAPI + LangGraph StateGraph               │
│                                                                   │
│  intake → RAG (OpenSearch) → LLM Router (Haiku) → parallel A2A  │
└─────────────────────────────┬─────────────────────────────────────┘
                              │  A2A HTTP — asyncio.gather
        ┌─────────────────────┼──────────────────────────┐
        ▼                     ▼                          ▼
  kdb-agent :8001       amps-agent :8002         portfolio-agent :8004
  Historical bond RFQs  AMPS Core positions      AMPS portfolio_nav
  (6-month Parquet)     live orders / mkt data
                                                 cds-agent :8005
                                                 AMPS cds_spreads

                                                 etf-agent :8006
                                                 AMPS etf_nav

                                                 risk-pnl-agent :8007
                                                 AMPS risk_metrics
        │
        ▼
  Confidence scoring → Synthesizer (Sonnet) → Response
  HIGH / MEDIUM / LOW  per-data-point [HIGH]/[LOW] tags
```

### LLM Provider

| Environment | Provider | Auth |
|-------------|----------|------|
| **AWS (production)** | `LLM_PROVIDER=bedrock` | ECS task IAM role — no API key needed |
| **Local dev** | `LLM_PROVIDER=anthropic` | `ANTHROPIC_API_KEY` in `.env` |
| **Local dev (free)** | `LLM_PROVIDER=ollama` | None — local Llama 3.2 |
| **Demos / CI** | `LLM_PROVIDER=mock` | None — returns static strings |

Bedrock models used:
- **Synthesis**: `us.anthropic.claude-sonnet-4-6-20251101-v1:0`
- **Routing**: `us.anthropic.claude-haiku-4-5-20251001-v1:0`

---

## Repository Map

Each directory is an independent module. You can clone the full monorepo or use each piece separately.

| Directory | Role | Deploy to |
|-----------|------|-----------|
| [`repo-api/`](repo-api/README.md) | FastAPI service + LangGraph + all 7 specialist agents | ECS Fargate (single Docker image) |
| [`repo-infra/`](repo-infra/README.md) | Terraform — VPC, ECS, ALB, DynamoDB, Cloud Map, Bedrock IAM | AWS |
| [`repo-local-dev/`](repo-local-dev/README.md) | Docker Compose profiles for local development | Local |
| [`repo-mcp-tools/`](repo-mcp-tools/README.md) | MCP servers for AMPS, KDB+, Portfolio, CDS, ETF data | ECS (optional) |
| [`repo-rag-ingest/`](repo-rag-ingest/README.md) | One-time ingestion scripts to populate OpenSearch | Local / CI |

---

## Quick Start — Local Development

**Minimal (MacBook-friendly, 1 agent container):**
```bash
cd repo-local-dev
# Add your Anthropic API key to .env
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env

docker compose --profile solo build
docker compose --profile solo up -d

curl -s http://localhost:8000/
```

**Full stack with all 7 specialist agents:**
```bash
cd repo-local-dev
docker compose --profile agents build
docker compose --profile agents up -d
```

See [repo-local-dev/README.md](repo-local-dev/README.md) for all profiles and options.

---

## Quick Start — AWS Deployment

**Prerequisites:** AWS CLI configured, Terraform ≥ 1.5, Docker, ECR access.

```bash
# 1. Deploy infrastructure
cd repo-infra
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: set aws_region, environment, image_tag
terraform init
terraform apply

# 2. Build and push the Docker image
ECR_URL=$(terraform output -raw ecr_api_repository_url)
IMAGE_TAG=$(git rev-parse --short HEAD)

aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin ${ECR_URL%/*}

docker build -f repo-api/Dockerfile -t ${ECR_URL}:${IMAGE_TAG} .
docker push ${ECR_URL}:${IMAGE_TAG}

# 3. Redeploy ECS with the new image
TF_VAR_image_tag=${IMAGE_TAG} terraform apply -auto-approve

# 4. Populate secrets (Langfuse keys, Brave search — NOT Anthropic, Bedrock uses IAM)
SECRET_ARN=$(terraform output -raw app_secret_arn)
aws secretsmanager put-secret-value \
  --secret-id ${SECRET_ARN} \
  --secret-string '{
    "BRAVE_API_KEY": "",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-...",
    "LANGFUSE_SECRET_KEY": "sk-lf-..."
  }'

# 5. Test
ALB=$(terraform output -raw alb_dns_name)
curl -s http://${ALB}/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Who are the top HY traders by hit rate?"}]}' \
  | jq .choices[0].message.content
```

See [repo-infra/README.md](repo-infra/README.md) for the full deployment guide.

---

## Key Design Decisions

**Single Docker image, multiple agents.** All 7 specialist agents and the API gateway run from the same Docker image. The `AGENT_SERVICE` environment variable selects which service starts (`api`, `kdb`, `amps`, `portfolio`, `cds`, `etf`, `risk_pnl`). This means one ECR repository and one build pipeline.

**DynamoDB service discovery.** Agents self-register on startup with a 90-second TTL. The API reads the registry on each request — no hardcoded URLs in production. In local dev, LocalStack emulates DynamoDB.

**Priority-aware routing.** The LLM Router classifies each selected agent as `required` (response is needed to answer the query) or `optional` (enriches the answer). Confidence is `HIGH` when all required agents responded, `MEDIUM` when only optional agents timed out, `LOW` when a required agent failed. Traders always get an answer, never a 500 error.

**Bedrock IAM auth.** In AWS, no API keys are stored anywhere. The ECS task role has `bedrock:InvokeModel` permission. Keys are only needed for local development.

---

## Cost Estimate (AWS, staging, 24/7)

| Resource | $/month |
|----------|---------|
| ECS Fargate — API (1 vCPU, 2 GB) | ~$30 |
| ECS Fargate — 6 agents (0.5 vCPU, 1 GB each) | ~$55 |
| ALB | ~$20 |
| NAT Gateway | ~$35 |
| VPC Interface Endpoints (6) | ~$50 |
| DynamoDB (on-demand) | ~$2 |
| CloudWatch Logs | ~$5 |
| **Total** | **~$200** |

Bedrock is billed per token: ~$0.003/query for Sonnet synthesis + $0.0003 for Haiku routing.

To reduce cost: set `desired_count = 0` on agents not in use, or remove NAT Gateway and use VPC endpoints instead.
