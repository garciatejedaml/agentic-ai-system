# repo-local-dev — Local Development Environment

Docker Compose stacks and scripts for running the full system locally
using LocalStack (free AWS emulator) instead of real AWS.

## Structure

```
docker-compose.localstack.yml   ← LocalStack: DynamoDB, SQS, S3, Secrets Manager
docker-compose.amps.yml         ← AMPS messaging server (requires binary)
docker-compose.kdb.yml          ← KDB+ server (requires license)
docker-compose.observability.yml ← Langfuse tracing UI
docker-compose.phase2.yml       ← Phase 2: all 5 A2A services + LocalStack
scripts/
  localstack_init.sh            ← Creates all AWS resources in LocalStack on startup
  test_amps_realtime.py         ← AMPS canary test (publish + subscribe round-trip)
  amps_publisher.py             ← Test data publisher for AMPS topics
docker/
  clickhouse/                   ← ClickHouse config for Langfuse backend
```

## Quick start (Phase 1 — monolith)

```bash
# 1. Start LocalStack (creates all DynamoDB tables, SQS queues, etc.)
docker compose -f docker-compose.localstack.yml up -d

# 2. (Optional) Start AMPS server — requires binary at repo-mcp-tools/docker/amps/AMPS.tar
docker compose -f docker-compose.amps.yml up -d

# 3. (Optional) Start KDB+ server — requires license at repo-mcp-tools/docker/kdb/kc.lic
docker compose -f docker-compose.kdb.yml up -d

# 4. (Optional) Start Langfuse observability
docker compose -f docker-compose.observability.yml up -d

# 5. Run the API (from monorepo root)
AWS_ENDPOINT_URL=http://localhost:4566 \
LLM_PROVIDER=anthropic \
ANTHROPIC_API_KEY=sk-ant-... \
uvicorn repo-api/src/api/server:app --reload
```

## Phase 2 — A2A multi-agent stack

```bash
# Build image from monorepo root
docker build -f repo-api/Dockerfile -t agentic-ai-system:phase2 .

# Start all 5 services (LocalStack + 3 agents + API gateway)
docker compose -f docker-compose.phase2.yml up -d

# Verify
curl http://localhost:8001/.well-known/agent.json   # KDB Agent card
curl http://localhost:8002/.well-known/agent.json   # AMPS Agent card
curl http://localhost:8003/.well-known/agent.json   # Financial Orchestrator card
curl http://localhost:8000/                          # API health

# Check agent registry
aws --endpoint-url=http://localhost:4566 --region us-east-1 \
    dynamodb scan --table-name agentic-ai-staging-agent-registry
```

## Test scripts

```bash
# AMPS real-time round-trip test
python scripts/test_amps_realtime.py

# Publish test messages to AMPS topics
python scripts/amps_publisher.py
```
