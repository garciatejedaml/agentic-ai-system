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
      { name = "LLM_PROVIDER",       value = "bedrock" },
      { name = "AWS_DEFAULT_REGION", value = local.region },

      # Model IDs (Bedrock cross-region inference profiles)
      { name = "BEDROCK_MODEL",      value = local.bedrock_model_sonnet },
      { name = "BEDROCK_FAST_MODEL", value = local.bedrock_model_haiku },

      # RAG — Amazon OpenSearch Service
      { name = "OPENSEARCH_URL",   value = "https://${aws_opensearch_domain.main.endpoint}" },
      { name = "OPENSEARCH_INDEX", value = "agentic-ai-knowledge-base" },

      # KDB historical data
      { name = "KDB_DATA_PATH", value = "/app/data/kdb" },
      { name = "KDB_ENABLED",   value = var.kdb_enabled },
      { name = "KDB_MODE",      value = "poc" },

      # AMPS (disabled by default — requires separate AMPS server)
      { name = "AMPS_ENABLED", value = var.amps_enabled },

      # Phase 3 specialist agent URLs (ECS internal DNS)
      { name = "AGENT_SERVICE",              value = "api" },
      { name = "AGENT_REGISTRY_TABLE",       value = "${local.name_prefix}-agent-registry" },
      { name = "KDB_AGENT_URL",              value = "http://${local.name_prefix}-kdb-agent.${var.environment}.local:8001" },
      { name = "AMPS_AGENT_URL",             value = "http://${local.name_prefix}-amps-agent.${var.environment}.local:8002" },
      { name = "FINANCIAL_ORCHESTRATOR_URL", value = "http://${local.name_prefix}-financial-orchestrator.${var.environment}.local:8003" },
      { name = "PORTFOLIO_AGENT_URL",        value = "http://${local.name_prefix}-portfolio-agent.${var.environment}.local:8004" },
      { name = "CDS_AGENT_URL",              value = "http://${local.name_prefix}-cds-agent.${var.environment}.local:8005" },
      { name = "ETF_AGENT_URL",              value = "http://${local.name_prefix}-etf-agent.${var.environment}.local:8006" },
      { name = "RISK_PNL_AGENT_URL",         value = "http://${local.name_prefix}-risk-pnl-agent.${var.environment}.local:8007" },

      # Observability (enable once Langfuse is deployed and LANGFUSE_* secrets set)
      { name = "OBSERVABILITY_ENABLED", value = "false" },

      # Server tuning
      { name = "PORT",            value = "8000" },
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
      {
        name      = "DYNATRACE_API_TOKEN"
        valueFrom = "${aws_secretsmanager_secret.app.arn}:DYNATRACE_API_TOKEN::"
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

# ── Phase 2: A2A Agent Task Definitions ──────────────────────────────────────
# Each agent runs as a separate ECS Fargate task with AGENT_SERVICE env var
# selecting which service to start (via phase2_entrypoint.sh).

locals {
  agent_common_env = [
    { name = "LLM_PROVIDER",         value = "bedrock" },
    { name = "AWS_DEFAULT_REGION",   value = local.region },
    { name = "BEDROCK_MODEL",        value = local.bedrock_model_sonnet },
    { name = "BEDROCK_FAST_MODEL",   value = local.bedrock_model_haiku },
    { name = "KDB_ENABLED",          value = var.kdb_enabled },
    { name = "KDB_MODE",             value = "poc" },
    { name = "KDB_DATA_PATH",        value = "/app/data/kdb" },
    { name = "AMPS_ENABLED",         value = var.amps_enabled },
    { name = "AGENT_REGISTRY_TABLE", value = "${local.name_prefix}-agent-registry" },
    { name = "OPENSEARCH_URL",       value = "https://${aws_opensearch_domain.main.endpoint}" },
    { name = "OPENSEARCH_INDEX",     value = "agentic-ai-knowledge-base" },
    { name = "SKIP_INGEST",          value = "true" },  # agents don't ingest; api-service does

    # Phase 4: Guardrails
    { name = "AGENT_MAX_ITERATIONS", value = "15" },
    { name = "GRAPH_RECURSION_LIMIT", value = "25" },
    { name = "AGENT_TIMEOUT_DEFAULT", value = "60" },
    { name = "AGENT_TIMEOUT_KDB",     value = "90" },
    { name = "AGENT_TIMEOUT_AMPS",    value = "30" },
    { name = "AGENT_TIMEOUT_RISK_PNL", value = "90" },

    # Phase 4: Rate limiting
    { name = "RATE_LIMIT_ENABLED",   value = "true" },
    { name = "DAILY_REQUEST_LIMIT",  value = "1000" },
    { name = "TOKEN_USAGE_TABLE",    value = "${local.name_prefix}-token-usage" },

    # Phase 4: Dynatrace OTel (DYNATRACE_API_TOKEN injected via Secrets Manager)
    { name = "DYNATRACE_ENDPOINT",   value = "" },  # set via var or SSM if needed
  ]
}

# ── KDB Agent ─────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "kdb_agent" {
  name              = "/agentic-ai/${var.environment}/kdb-agent"
  retention_in_days = 30
}

resource "aws_ecs_task_definition" "kdb_agent" {
  family                   = "${local.name_prefix}-kdb-agent"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  task_role_arn            = aws_iam_role.ecs_task.arn
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name  = "kdb-agent"
    image = local.ecr_api_image

    portMappings = [{ containerPort = 8001, protocol = "tcp" }]

    environment = concat(local.agent_common_env, [
      { name = "AGENT_SERVICE", value = "kdb" },
      { name = "AGENT_PORT",    value = "8001" },
    ])

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.kdb_agent.name
        "awslogs-region"        = local.region
        "awslogs-stream-prefix" = "kdb-agent"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8001/health || exit 1"]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 30
    }

    essential = true
  }])
}

resource "aws_ecs_service" "kdb_agent" {
  name            = "${local.name_prefix}-kdb-agent"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.kdb_agent.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.kdb_agent.arn
    container_name   = "kdb-agent"
    container_port   = 8001
  }

  lifecycle { ignore_changes = [desired_count] }
  depends_on = [aws_lb_listener.http, aws_iam_role_policy_attachment.ecs_execution_standard]
}

# ── AMPS Agent ────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "amps_agent" {
  name              = "/agentic-ai/${var.environment}/amps-agent"
  retention_in_days = 30
}

resource "aws_ecs_task_definition" "amps_agent" {
  family                   = "${local.name_prefix}-amps-agent"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  task_role_arn            = aws_iam_role.ecs_task.arn
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name  = "amps-agent"
    image = local.ecr_api_image

    portMappings = [{ containerPort = 8002, protocol = "tcp" }]

    environment = concat(local.agent_common_env, [
      { name = "AGENT_SERVICE", value = "amps" },
      { name = "AGENT_PORT",    value = "8002" },
      { name = "AMPS_HOST",     value = var.amps_host },
      { name = "AMPS_PORT",     value = tostring(var.amps_tcp_port) },
    ])

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.amps_agent.name
        "awslogs-region"        = local.region
        "awslogs-stream-prefix" = "amps-agent"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8002/health || exit 1"]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 30
    }

    essential = true
  }])
}

resource "aws_ecs_service" "amps_agent" {
  name            = "${local.name_prefix}-amps-agent"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.amps_agent.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.amps_agent.arn
    container_name   = "amps-agent"
    container_port   = 8002
  }

  lifecycle { ignore_changes = [desired_count] }
  depends_on = [aws_lb_listener.http, aws_iam_role_policy_attachment.ecs_execution_standard]
}

# ── Financial Orchestrator ────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "financial_orchestrator" {
  name              = "/agentic-ai/${var.environment}/financial-orchestrator"
  retention_in_days = 30
}

resource "aws_ecs_task_definition" "financial_orchestrator" {
  family                   = "${local.name_prefix}-financial-orchestrator"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 1024
  memory                   = 2048
  task_role_arn            = aws_iam_role.ecs_task.arn
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name  = "financial-orchestrator"
    image = local.ecr_api_image

    portMappings = [{ containerPort = 8003, protocol = "tcp" }]

    environment = concat(local.agent_common_env, [
      { name = "AGENT_SERVICE",           value = "financial_orchestrator" },
      { name = "AGENT_PORT",              value = "8003" },
      # A2A endpoints resolved via DynamoDB registry at runtime;
      # env vars are fallbacks if DynamoDB is unavailable
      { name = "KDB_AGENT_URL",           value = "http://${local.name_prefix}-kdb-agent.internal:8001" },
      { name = "AMPS_AGENT_URL",          value = "http://${local.name_prefix}-amps-agent.internal:8002" },
    ])

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.financial_orchestrator.name
        "awslogs-region"        = local.region
        "awslogs-stream-prefix" = "financial-orchestrator"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8003/health || exit 1"]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 45
    }

    essential = true
  }])
}

resource "aws_ecs_service" "financial_orchestrator" {
  name            = "${local.name_prefix}-financial-orchestrator"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.financial_orchestrator.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.financial_orchestrator.arn
    container_name   = "financial-orchestrator"
    container_port   = 8003
  }

  lifecycle { ignore_changes = [desired_count] }
  depends_on = [aws_lb_listener.http, aws_iam_role_policy_attachment.ecs_execution_standard]
}

# ── Phase 3: Portfolio Agent ──────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "portfolio_agent" {
  name              = "/agentic-ai/${var.environment}/portfolio-agent"
  retention_in_days = 30
}

resource "aws_ecs_task_definition" "portfolio_agent" {
  family                   = "${local.name_prefix}-portfolio-agent"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  task_role_arn            = aws_iam_role.ecs_task.arn
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name  = "portfolio-agent"
    image = local.ecr_api_image
    portMappings = [{ containerPort = 8004, protocol = "tcp" }]
    environment = concat(local.agent_common_env, [
      { name = "AGENT_SERVICE", value = "portfolio" },
      { name = "AGENT_PORT",    value = "8004" },
    ])
    logConfiguration = {
      logDriver = "awslogs"
      options   = { "awslogs-group" = aws_cloudwatch_log_group.portfolio_agent.name, "awslogs-region" = local.region, "awslogs-stream-prefix" = "portfolio-agent" }
    }
    healthCheck = { command = ["CMD-SHELL", "curl -f http://localhost:8004/health || exit 1"], interval = 30, timeout = 10, retries = 3, startPeriod = 30 }
    essential = true
  }])
}

resource "aws_ecs_service" "portfolio_agent" {
  name            = "${local.name_prefix}-portfolio-agent"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.portfolio_agent.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.portfolio_agent.arn
    container_name   = "portfolio-agent"
    container_port   = 8004
  }
  lifecycle { ignore_changes = [desired_count] }
  depends_on = [aws_lb_listener.http, aws_iam_role_policy_attachment.ecs_execution_standard]
}

# ── Phase 3: CDS Agent ────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "cds_agent" {
  name              = "/agentic-ai/${var.environment}/cds-agent"
  retention_in_days = 30
}

resource "aws_ecs_task_definition" "cds_agent" {
  family                   = "${local.name_prefix}-cds-agent"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  task_role_arn            = aws_iam_role.ecs_task.arn
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name  = "cds-agent"
    image = local.ecr_api_image
    portMappings = [{ containerPort = 8005, protocol = "tcp" }]
    environment = concat(local.agent_common_env, [
      { name = "AGENT_SERVICE", value = "cds" },
      { name = "AGENT_PORT",    value = "8005" },
    ])
    logConfiguration = {
      logDriver = "awslogs"
      options   = { "awslogs-group" = aws_cloudwatch_log_group.cds_agent.name, "awslogs-region" = local.region, "awslogs-stream-prefix" = "cds-agent" }
    }
    healthCheck = { command = ["CMD-SHELL", "curl -f http://localhost:8005/health || exit 1"], interval = 30, timeout = 10, retries = 3, startPeriod = 30 }
    essential = true
  }])
}

resource "aws_ecs_service" "cds_agent" {
  name            = "${local.name_prefix}-cds-agent"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.cds_agent.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.cds_agent.arn
    container_name   = "cds-agent"
    container_port   = 8005
  }
  lifecycle { ignore_changes = [desired_count] }
  depends_on = [aws_lb_listener.http, aws_iam_role_policy_attachment.ecs_execution_standard]
}

# ── Phase 3: ETF Agent ────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "etf_agent" {
  name              = "/agentic-ai/${var.environment}/etf-agent"
  retention_in_days = 30
}

resource "aws_ecs_task_definition" "etf_agent" {
  family                   = "${local.name_prefix}-etf-agent"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  task_role_arn            = aws_iam_role.ecs_task.arn
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name  = "etf-agent"
    image = local.ecr_api_image
    portMappings = [{ containerPort = 8006, protocol = "tcp" }]
    environment = concat(local.agent_common_env, [
      { name = "AGENT_SERVICE", value = "etf" },
      { name = "AGENT_PORT",    value = "8006" },
    ])
    logConfiguration = {
      logDriver = "awslogs"
      options   = { "awslogs-group" = aws_cloudwatch_log_group.etf_agent.name, "awslogs-region" = local.region, "awslogs-stream-prefix" = "etf-agent" }
    }
    healthCheck = { command = ["CMD-SHELL", "curl -f http://localhost:8006/health || exit 1"], interval = 30, timeout = 10, retries = 3, startPeriod = 30 }
    essential = true
  }])
}

resource "aws_ecs_service" "etf_agent" {
  name            = "${local.name_prefix}-etf-agent"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.etf_agent.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.etf_agent.arn
    container_name   = "etf-agent"
    container_port   = 8006
  }
  lifecycle { ignore_changes = [desired_count] }
  depends_on = [aws_lb_listener.http, aws_iam_role_policy_attachment.ecs_execution_standard]
}

# ── Phase 3: Risk & P&L Agent ─────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "risk_pnl_agent" {
  name              = "/agentic-ai/${var.environment}/risk-pnl-agent"
  retention_in_days = 30
}

resource "aws_ecs_task_definition" "risk_pnl_agent" {
  family                   = "${local.name_prefix}-risk-pnl-agent"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  task_role_arn            = aws_iam_role.ecs_task.arn
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name  = "risk-pnl-agent"
    image = local.ecr_api_image
    portMappings = [{ containerPort = 8007, protocol = "tcp" }]
    environment = concat(local.agent_common_env, [
      { name = "AGENT_SERVICE",    value = "risk_pnl" },
      { name = "AGENT_PORT",       value = "8007" },
      { name = "PORTFOLIO_AGENT_URL", value = "http://${local.name_prefix}-portfolio-agent.${var.environment}.local:8004" },
      { name = "KDB_AGENT_URL",       value = "http://${local.name_prefix}-kdb-agent.${var.environment}.local:8001" },
    ])
    logConfiguration = {
      logDriver = "awslogs"
      options   = { "awslogs-group" = aws_cloudwatch_log_group.risk_pnl_agent.name, "awslogs-region" = local.region, "awslogs-stream-prefix" = "risk-pnl-agent" }
    }
    healthCheck = { command = ["CMD-SHELL", "curl -f http://localhost:8007/health || exit 1"], interval = 30, timeout = 10, retries = 3, startPeriod = 30 }
    essential = true
  }])
}

resource "aws_ecs_service" "risk_pnl_agent" {
  name            = "${local.name_prefix}-risk-pnl-agent"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.risk_pnl_agent.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.risk_pnl_agent.arn
    container_name   = "risk-pnl-agent"
    container_port   = 8007
  }
  lifecycle { ignore_changes = [desired_count] }
  depends_on = [aws_lb_listener.http, aws_iam_role_policy_attachment.ecs_execution_standard]
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
