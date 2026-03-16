# repo-local-dev — Local Development Environment

Docker Compose stacks for running the full Agentic AI System locally. Uses **LocalStack** to emulate AWS (DynamoDB, SQS, Secrets Manager, S3) so you can develop without an AWS account.

---

## Profiles

Choose the profile that fits your machine and use case:

| Profile | Containers | Use when |
|---------|-----------|----------|
| `solo` | LocalStack + 1 generic agent + API | MacBook dev — minimal memory, full pipeline tested |
| `demo` | LocalStack + API | Presentations — set `DEMO_MODE_ENABLED=true` for scripted responses |
| `agents` | LocalStack + API + all 7 specialist agents | Full feature testing |
| `amps` | 5 AMPS server instances + publishers | Live real-time data (requires AMPS binary) |
| `rag` | OpenSearch vector store | Semantic search / RAG testing |

Profiles can be combined: `--profile agents --profile amps --profile rag`

---

## Prerequisites

- Docker Desktop (4 GB RAM minimum; 8 GB recommended for `agents` profile)
- For `amps` profile: AMPS binary at `docker/amps/AMPS-*.tar.gz` (from crankuptheamps.com)

---

## Configuration

Copy the example and fill in your keys:

```bash
cp .env.example .env   # if .env.example exists, otherwise edit .env directly
```

**.env reference:**

```bash
# LLM provider — use "anthropic" for local dev, "bedrock" for AWS, "ollama" for free local
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...        # required when LLM_PROVIDER=anthropic

# Demo mode — returns pre-scripted responses, no API key needed
DEMO_MODE_ENABLED=false

# Observability — Langfuse traces (optional; keys below work with local Langfuse stack)
OBSERVABILITY_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-local-dev
LANGFUSE_SECRET_KEY=sk-lf-local-dev
LANGFUSE_HOST=http://langfuse-web:3000

# Solo mode — all 7 agent IDs in DynamoDB point to a single generic container
SOLO_MODE=true   # set to true when using --profile solo
```

> **Note:** `.env` does not support inline comments. Put `KEY=value` on its own line.

---

## Profile: solo (recommended for MacBook)

Runs 3 containers. All 7 agent IDs in DynamoDB point to one `generic-agent` container, so the full pipeline (LLM Router → DynamoDB discovery → A2A → confidence scoring → synthesis) is exercised with minimal resources.

```bash
# .env: set SOLO_MODE=true and your ANTHROPIC_API_KEY

docker compose --profile solo build   # first time only
docker compose --profile solo up -d

# Verify
curl http://localhost:8000/

# Query
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"x","messages":[{"role":"user","content":"Who are the top HY traders by hit rate?"}]}' \
  | jq .choices[0].message.content

# Check agent registry in DynamoDB
docker exec localstack awslocal dynamodb scan \
  --table-name agentic-ai-staging-agent-registry \
  --query 'Items[].{id:agent_id.S,url:endpoint.S}' --output table
```

---

## Profile: demo (no API key)

Runs the API and LocalStack only. Useful for presentations where you want consistent, fast responses.

```bash
# .env: set DEMO_MODE_ENABLED=true

docker compose --profile demo up -d

curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"x","messages":[{"role":"user","content":"show me HY portfolio exposure"}]}' \
  | jq .choices[0].message.content
```

---

## Profile: agents (full stack)

Runs all 7 specialist agents at their real ports.

```bash
docker compose --profile agents build
docker compose --profile agents up -d

# Agent health checks
curl http://localhost:8001/health   # kdb-agent
curl http://localhost:8004/health   # portfolio-agent
curl http://localhost:8005/health   # cds-agent
curl http://localhost:8007/health   # risk-pnl-agent
```

Agent ports:

| Port | Container | Data source |
|------|-----------|-------------|
| 8000 | api-service | LangGraph orchestrator |
| 8001 | kdb-agent | KDB+ / Parquet (bond RFQ history) |
| 8002 | amps-agent | AMPS Core (positions, orders) |
| 8003 | financial-orchestrator | Phase 2 fallback |
| 8004 | portfolio-agent | AMPS portfolio_nav topic |
| 8005 | cds-agent | AMPS cds_spreads topic |
| 8006 | etf-agent | AMPS etf_nav topic |
| 8007 | risk-pnl-agent | AMPS risk_metrics topic |
| 4566 | localstack | DynamoDB, SQS, S3 emulation |

---

## Profile: amps (live AMPS data)

Requires the AMPS binary. Start alongside `agents` to feed live real-time data:

```bash
# Build AMPS image (requires binary at docker/amps/AMPS-*.tar.gz)
docker compose --profile amps build

# Start agents + AMPS
docker compose --profile agents --profile amps up -d
```

AMPS admin consoles (once running):

| URL | Instance |
|-----|----------|
| http://localhost:8085 | amps-core (positions/orders) |
| http://localhost:8086 | amps-portfolio |
| http://localhost:8087 | amps-cds |
| http://localhost:8088 | amps-etf |
| http://localhost:8089 | amps-risk |

---

## Profile: rag (OpenSearch)

Adds an OpenSearch instance for semantic search. Run ingestion first (see `repo-rag-ingest/`):

```bash
docker compose --profile rag up -d
# Then run ingestion scripts from repo-rag-ingest/
```

---

## Observability (Langfuse)

Start the observability stack separately before the API:

```bash
docker compose -f docker-compose.observability.yml up -d
# Langfuse UI: http://localhost:3000  (admin@example.com / changeme)
```

The API connects to Langfuse automatically when `OBSERVABILITY_ENABLED=true` and the keys match.

---

## Useful commands

```bash
# View logs
docker compose --profile solo logs -f api-service
docker compose --profile solo logs -f generic-agent
docker compose --profile solo logs -f localstack

# Restart a single container (e.g. after code change + rebuild)
docker compose --profile solo build && docker compose --profile solo up -d

# Check DynamoDB tables
docker exec localstack awslocal dynamodb list-tables

# Check agent registry
docker exec localstack awslocal dynamodb scan \
  --table-name agentic-ai-staging-agent-registry \
  --query 'Items[].{id:agent_id.S,url:endpoint.S}' --output table

# Stop everything
docker compose --profile solo down
docker compose --profile agents --profile amps --profile rag down

# Full reset (removes volumes — deletes all DynamoDB data)
docker compose --profile solo down -v
```
