# ── ECS Task Role ─────────────────────────────────────────────────────────────
# Permissions granted TO the running container (what the application can do).

resource "aws_iam_role" "ecs_task" {
  name        = "${local.name_prefix}-ecs-task-role"
  description = "Grants ECS tasks access to Bedrock, SQS, DynamoDB, Secrets Manager"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "ecs_task_permissions" {
  name = "${local.name_prefix}-ecs-task-permissions"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # ── Bedrock: invoke Claude models ─────────────────────────────────────
      {
        Sid    = "BedrockInvoke"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
        ]
        Resource = "*"
        # Scope to specific model ARNs in production if desired:
        # Resource = "arn:aws:bedrock:*::foundation-model/anthropic.claude-*"
      },
      # ── SQS: async job queue ───────────────────────────────────────────────
      {
        Sid    = "SqsJobQueue"
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
        ]
        Resource = [
          aws_sqs_queue.jobs.arn,
          aws_sqs_queue.jobs_dlq.arn,
        ]
      },
      # ── DynamoDB: agent registry ───────────────────────────────────────────
      {
        Sid    = "DynamoAgentRegistry"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:PutItem",   # agents self-register on startup
        ]
        Resource = [
          aws_dynamodb_table.agent_registry.arn,
          "${aws_dynamodb_table.agent_registry.arn}/index/*",
        ]
      },
      # ── Secrets Manager: read app secrets at runtime ───────────────────────
      {
        Sid      = "SecretsRead"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = aws_secretsmanager_secret.app.arn
      },
      # ── CloudWatch: custom metrics (LangGraph span publishing) ────────────
      {
        Sid      = "CloudWatchMetrics"
        Effect   = "Allow"
        Action   = ["cloudwatch:PutMetricData"]
        Resource = "*"
      },
    ]
  })
}

# ── ECS Execution Role ────────────────────────────────────────────────────────
# Used by the ECS control plane to start the container (not by the app itself).
# Needs: pull image from ECR, write startup logs, read secrets for env injection.

resource "aws_iam_role" "ecs_execution" {
  name        = "${local.name_prefix}-ecs-execution-role"
  description = "ECS control plane: ECR pull + CloudWatch logs + Secrets env injection"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Attach the standard ECS execution policy (ECR + CloudWatch)
resource "aws_iam_role_policy_attachment" "ecs_execution_standard" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow execution role to read secrets for env var injection into task
resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "${local.name_prefix}-execution-secrets"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "SecretsForEnvInjection"
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = aws_secretsmanager_secret.app.arn
    }]
  })
}
