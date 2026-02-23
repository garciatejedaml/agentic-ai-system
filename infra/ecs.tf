# ── CloudWatch Log Group ──────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "api" {
  name              = "/agentic-ai/${var.environment}/api"
  retention_in_days = 30
}

# ── ECS Cluster ───────────────────────────────────────────────────────────────

resource "aws_ecs_cluster" "main" {
  name = "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}

# ── ECS Task Definition ───────────────────────────────────────────────────────

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name_prefix}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  task_role_arn            = aws_iam_role.ecs_task.arn
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name  = "api"
    image = local.ecr_api_image

    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    # ── Static environment variables ────────────────────────────────────────
    environment = [
      # Use Bedrock in production — no API key needed (IAM auth via task_role)
      { name = "LLM_PROVIDER",         value = "bedrock" },
      { name = "AWS_DEFAULT_REGION",   value = local.region },

      # Model IDs (Bedrock cross-region inference profiles)
      { name = "BEDROCK_MODEL",          value = local.bedrock_model_sonnet },
      { name = "ANTHROPIC_FAST_MODEL",   value = local.bedrock_model_haiku },

      # RAG
      { name = "CHROMA_PERSIST_DIR", value = "/data/chroma_db" },
      { name = "KDB_DATA_PATH",      value = "/app/data/kdb" },
      { name = "KDB_ENABLED",        value = var.kdb_enabled },
      { name = "KDB_MODE",           value = "poc" },

      # AMPS (disabled by default — requires separate AMPS server)
      { name = "AMPS_ENABLED", value = var.amps_enabled },

      # Observability (enable once Langfuse is deployed and LANGFUSE_* secrets set)
      { name = "OBSERVABILITY_ENABLED", value = "false" },

      # Server tuning
      { name = "PORT",             value = "8000" },
      { name = "UVICORN_WORKERS", value = "2" },
      { name = "LOG_LEVEL",       value = var.log_level },
      { name = "SKIP_INGEST",     value = var.skip_ingest },
    ]

    # ── Secrets injected from Secrets Manager at container start ────────────
    # ECS reads these from Secrets Manager and injects as env vars.
    # Secrets Manager JSON key path: secretsmanager:arn:json-key
    secrets = [
      {
        name      = "BRAVE_API_KEY"
        valueFrom = "${aws_secretsmanager_secret.app.arn}:BRAVE_API_KEY::"
      },
      {
        name      = "LANGFUSE_PUBLIC_KEY"
        valueFrom = "${aws_secretsmanager_secret.app.arn}:LANGFUSE_PUBLIC_KEY::"
      },
      {
        name      = "LANGFUSE_SECRET_KEY"
        valueFrom = "${aws_secretsmanager_secret.app.arn}:LANGFUSE_SECRET_KEY::"
      },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = local.region
        "awslogs-stream-prefix" = "api"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8000/ || exit 1"]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 60 # allow time for doc ingestion on cold start
    }

    essential = true
  }])
}

# ── ECS Fargate Service ───────────────────────────────────────────────────────

resource "aws_ecs_service" "api" {
  name            = "${local.name_prefix}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.service_desired_count

  # Rolling deployment: always keep at least 1 task healthy during deploys
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  launch_type = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  # Ignore desired_count changes after deploy (managed by auto-scaling)
  lifecycle {
    ignore_changes = [desired_count]
  }

  depends_on = [
    aws_lb_listener.http,
    aws_iam_role_policy_attachment.ecs_execution_standard,
  ]
}
