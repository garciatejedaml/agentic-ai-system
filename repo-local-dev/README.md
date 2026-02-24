# repo-local-dev — Local Development Environment

Docker Compose stacks and scripts for running the full system locally
using LocalStack (free AWS emulator) instead of real AWS.

## Structure

```
docker-compose.localstack.yml   ← LocalStack: DynamoDB, SQS, S3, Secrets Manager
docker-compose.amps.yml         ← AMPS messaging server (requires binary)
docker-compose.kdb.yml          ← KDB+ server (requires license)
docker-compose.observability.yml ← Langfuse tracing UI
scripts/
  localstack_init.sh            ← Creates all AWS resources in LocalStack on startup
  test_amps_realtime.py         ← AMPS canary test (publish + subscribe round-trip)
  amps_publisher.py             ← Test data publisher for AMPS topics
docker/
  clickhouse/                   ← ClickHouse config for Langfuse backend
```

## Quick start

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
uvicorn repo-api/src/api/server:app --app-dir repo-api --reload
```

## Test scripts

```bash
# AMPS real-time round-trip test
python scripts/test_amps_realtime.py

# Publish test messages to AMPS topics
python scripts/amps_publisher.py
```
