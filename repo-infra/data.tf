# ── Aurora Serverless v2 — pgvector ──────────────────────────────────────────
# Production replacement for ChromaDB.
# After first deploy, enable the extension once:
#   psql -h <aurora_endpoint> -U agenticai -d agenticai -c "CREATE EXTENSION IF NOT EXISTS vector;"

resource "aws_db_subnet_group" "aurora" {
  name        = "${local.name_prefix}-aurora-subnet-group"
  subnet_ids  = aws_subnet.isolated[*].id
  description = "Isolated subnets for Aurora Serverless v2"
}

resource "random_password" "aurora" {
  length  = 32
  special = false # Aurora doesn't allow all specials in the initial password
}

resource "aws_secretsmanager_secret" "aurora_credentials" {
  name        = "/${local.name_prefix}/aurora/credentials"
  description = "Aurora master credentials"
}

resource "aws_secretsmanager_secret_version" "aurora_credentials" {
  secret_id = aws_secretsmanager_secret.aurora_credentials.id
  secret_string = jsonencode({
    username = "agenticai"
    password = random_password.aurora.result
  })
}

resource "aws_rds_cluster" "pgvector" {
  cluster_identifier     = "${local.name_prefix}-aurora"
  engine                 = "aurora-postgresql"
  engine_version         = "15.4"
  database_name          = "agenticai"
  master_username        = "agenticai"
  master_password        = random_password.aurora.result
  db_subnet_group_name   = aws_db_subnet_group.aurora.name
  vpc_security_group_ids = [aws_security_group.data.id]
  storage_encrypted      = true
  deletion_protection    = var.aurora_deletion_protection
  skip_final_snapshot    = !var.aurora_deletion_protection

  serverlessv2_scaling_configuration {
    min_capacity = var.aurora_min_capacity
    max_capacity = var.aurora_max_capacity
  }

  tags = { Name = "${local.name_prefix}-aurora" }
}

resource "aws_rds_cluster_instance" "pgvector_writer" {
  identifier         = "${local.name_prefix}-aurora-writer"
  cluster_identifier = aws_rds_cluster.pgvector.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.pgvector.engine
  engine_version     = aws_rds_cluster.pgvector.engine_version

  tags = { Name = "${local.name_prefix}-aurora-writer" }
}

# ── DynamoDB — Agent Registry ─────────────────────────────────────────────────
# Multi-tenant agent platform pattern.
# Each team registers their agent here: agent_id, keywords, task_def_arn, etc.
# The orchestrator reads this table to discover which agents handle which queries.

resource "aws_dynamodb_table" "agent_registry" {
  name         = "${local.name_prefix}-agent-registry"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "agent_id"

  attribute {
    name = "agent_id"
    type = "S"
  }

  attribute {
    name = "desk_name"
    type = "S"
  }

  # GSI: query registered agents by trading desk
  global_secondary_index {
    name            = "ByDesk"
    hash_key        = "desk_name"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = { Name = "${local.name_prefix}-agent-registry" }
}

# ── SQS — Async Job Queue ─────────────────────────────────────────────────────
# Decouples API from long-running agent runs (>30s).
# API returns job_id immediately; client polls /v1/jobs/{id} for status.

resource "aws_sqs_queue" "jobs_dlq" {
  name                      = "${local.name_prefix}-jobs-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = { Name = "${local.name_prefix}-jobs-dlq" }
}

resource "aws_sqs_queue" "jobs" {
  name                       = "${local.name_prefix}-jobs"
  visibility_timeout_seconds = 900 # 15 min max agent run
  message_retention_seconds  = 21600 # 6 hours

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.jobs_dlq.arn
    maxReceiveCount     = 3
  })

  tags = { Name = "${local.name_prefix}-jobs" }
}

# ── Secrets Manager — App secrets bundle ─────────────────────────────────────
# Populate after first deploy:
#   aws secretsmanager put-secret-value \
#     --secret-id /agentic-ai-staging/app/secrets \
#     --secret-string '{"ANTHROPIC_API_KEY":"sk-ant-...","BRAVE_API_KEY":"BSA-...",...}'

resource "aws_secretsmanager_secret" "app" {
  name        = "/${local.name_prefix}/app/secrets"
  description = "Runtime secrets for the Agentic AI System"
}

resource "aws_secretsmanager_secret_version" "app_placeholder" {
  secret_id = aws_secretsmanager_secret.app.id

  # Placeholder values — replace via CLI after deploy (see infra/README.md)
  secret_string = jsonencode({
    ANTHROPIC_API_KEY   = "REPLACE_ME"
    BRAVE_API_KEY       = "REPLACE_ME"
    LANGFUSE_PUBLIC_KEY = "REPLACE_ME"
    LANGFUSE_SECRET_KEY = "REPLACE_ME"
  })

  # Ignore changes after initial creation so manual updates via CLI are preserved
  lifecycle {
    ignore_changes = [secret_string]
  }
}
