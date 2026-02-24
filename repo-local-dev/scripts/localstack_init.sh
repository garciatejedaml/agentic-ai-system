#!/bin/bash
# ── LocalStack init script ─────────────────────────────────────────────────────
# Runs automatically after LocalStack is ready (mounted at ready.d/).
# Creates all AWS resources that Terraform would provision in production.
#
# Resources created:
#   SQS  — job queue + dead-letter queue
#   DynamoDB — agent registry table (with GSI)
#   Secrets Manager — app secrets placeholder
#   S3   — Terraform remote state bucket (optional)
#   CloudWatch Logs — app log group

set -e

ENDPOINT="http://localhost:4566"
REGION="us-east-1"
export AWS_PAGER=""              # disable pager on CLI v1 and v2
export AWS_ACCESS_KEY_ID=test    # LocalStack accepts any non-empty value
export AWS_SECRET_ACCESS_KEY=test
AWS="aws --endpoint-url=${ENDPOINT} --region=${REGION}"

echo "[localstack-init] Creating AWS resources..."

# ── SQS: job queue + DLQ ──────────────────────────────────────────────────────

$AWS sqs create-queue \
  --queue-name agentic-ai-staging-jobs-dlq \
  --attributes '{"MessageRetentionPeriod":"1209600"}' \
  > /dev/null

DLQ_ARN=$($AWS sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/agentic-ai-staging-jobs-dlq \
  --attribute-names QueueArn \
  --query Attributes.QueueArn --output text)

$AWS sqs create-queue \
  --queue-name agentic-ai-staging-jobs \
  --attributes "{
    \"VisibilityTimeout\":\"900\",
    \"MessageRetentionPeriod\":\"21600\",
    \"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"
  }" > /dev/null

echo "[localstack-init] SQS: agentic-ai-staging-jobs + DLQ created"

# ── DynamoDB: agent registry ───────────────────────────────────────────────────

$AWS dynamodb create-table \
  --table-name agentic-ai-staging-agent-registry \
  --attribute-definitions \
    AttributeName=agent_id,AttributeType=S \
    AttributeName=desk_name,AttributeType=S \
  --key-schema AttributeName=agent_id,KeyType=HASH \
  --global-secondary-indexes '[{
    "IndexName": "ByDesk",
    "KeySchema": [{"AttributeName":"desk_name","KeyType":"HASH"}],
    "Projection": {"ProjectionType":"ALL"},
    "ProvisionedThroughput": {"ReadCapacityUnits":5,"WriteCapacityUnits":5}
  }]' \
  --billing-mode PAY_PER_REQUEST \
  > /dev/null

echo "[localstack-init] DynamoDB: agent registry table created"

# ── DynamoDB: session store ────────────────────────────────────────────────────

$AWS dynamodb create-table \
  --table-name agentic-ai-staging-sessions \
  --attribute-definitions \
    AttributeName=session_id,AttributeType=S \
    AttributeName=user_id,AttributeType=S \
  --key-schema AttributeName=session_id,KeyType=HASH \
  --global-secondary-indexes '[{
    "IndexName": "ByUser",
    "KeySchema": [{"AttributeName":"user_id","KeyType":"HASH"}],
    "Projection": {
      "ProjectionType":"INCLUDE",
      "NonKeyAttributes":["session_id","desk_name","created_at","updated_at","message_count"]
    },
    "ProvisionedThroughput": {"ReadCapacityUnits":5,"WriteCapacityUnits":5}
  }]' \
  --billing-mode PAY_PER_REQUEST \
  > /dev/null

echo "[localstack-init] DynamoDB: session store table created"

# ── Secrets Manager: app secrets ──────────────────────────────────────────────

$AWS secretsmanager create-secret \
  --name /agentic-ai-staging/app/secrets \
  --description "Runtime secrets for the Agentic AI System (LocalStack)" \
  --secret-string '{
    "ANTHROPIC_API_KEY": "REPLACE_WITH_REAL_KEY",
    "BRAVE_API_KEY":     "REPLACE_WITH_REAL_KEY",
    "LANGFUSE_PUBLIC_KEY": "REPLACE_ME",
    "LANGFUSE_SECRET_KEY": "REPLACE_ME"
  }' > /dev/null

echo "[localstack-init] Secrets Manager: /agentic-ai-staging/app/secrets created"

# ── S3: Terraform state bucket ────────────────────────────────────────────────

$AWS s3 mb s3://agentic-ai-terraform-state > /dev/null

# DynamoDB table for Terraform state locking
$AWS dynamodb create-table \
  --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  > /dev/null

echo "[localstack-init] S3: Terraform state bucket + DynamoDB lock table created"

# ── CloudWatch Logs ───────────────────────────────────────────────────────────

$AWS logs create-log-group \
  --log-group-name /agentic-ai/staging/api > /dev/null

echo "[localstack-init] CloudWatch Logs: /agentic-ai/staging/api created"

# ── Phase 2: Pre-register A2A agents in DynamoDB ──────────────────────────────
# Seeds the registry so the Financial Orchestrator can discover agents
# before containers have fully started (avoids cold-start race condition).
# Each container overwrites its entry with live status on startup.

TTL=$(( $(date +%s) + 3600 ))

$AWS dynamodb put-item \
  --table-name agentic-ai-staging-agent-registry \
  --item "{
    \"agent_id\":     {\"S\": \"kdb-agent\"},
    \"desk_name\":    {\"S\": \"HY\"},
    \"endpoint\":     {\"S\": \"http://kdb-agent:8001\"},
    \"capabilities\": {\"SS\": [\"bond_analytics\", \"trader_performance\", \"rfq_history\"]},
    \"status\":       {\"S\": \"registered\"},
    \"ttl\":          {\"N\": \"${TTL}\"}
  }" > /dev/null

$AWS dynamodb put-item \
  --table-name agentic-ai-staging-agent-registry \
  --item "{
    \"agent_id\":     {\"S\": \"amps-agent\"},
    \"desk_name\":    {\"S\": \"HY\"},
    \"endpoint\":     {\"S\": \"http://amps-agent:8002\"},
    \"capabilities\": {\"SS\": [\"realtime_positions\", \"live_orders\", \"market_data\"]},
    \"status\":       {\"S\": \"registered\"},
    \"ttl\":          {\"N\": \"${TTL}\"}
  }" > /dev/null

$AWS dynamodb put-item \
  --table-name agentic-ai-staging-agent-registry \
  --item "{
    \"agent_id\":     {\"S\": \"financial-orchestrator\"},
    \"desk_name\":    {\"S\": \"HY\"},
    \"endpoint\":     {\"S\": \"http://financial-orchestrator:8003\"},
    \"capabilities\": {\"SS\": [\"financial_analysis\", \"bond_trading\", \"multi_source\"]},
    \"status\":       {\"S\": \"registered\"},
    \"ttl\":          {\"N\": \"${TTL}\"}
  }" > /dev/null

echo "[localstack-init] DynamoDB: 3 A2A agents pre-registered in agent-registry"

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo "[localstack-init] ✓ All resources created. Endpoints:"
echo "  SQS:      ${ENDPOINT}/000000000000/agentic-ai-staging-jobs"
echo "  DynamoDB: ${ENDPOINT} (table: agentic-ai-staging-agent-registry)"
echo "  Secrets:  ${ENDPOINT} (secret: /agentic-ai-staging/app/secrets)"
echo "  S3:       ${ENDPOINT}/agentic-ai-terraform-state"
echo ""
echo "  A2A Agents pre-registered:"
echo "    kdb-agent              → http://kdb-agent:8001"
echo "    amps-agent             → http://amps-agent:8002"
echo "    financial-orchestrator → http://financial-orchestrator:8003"
echo ""
