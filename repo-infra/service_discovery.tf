# ── AWS Cloud Map — Private DNS Service Discovery ─────────────────────────────
#
# Enables ECS tasks to resolve each other by DNS name without going through
# the ALB. Each agent ECS service registers with Cloud Map on startup and
# de-registers when the task stops.
#
# DNS pattern: {name_prefix}-{agent}.{environment}.local:{port}
# Examples:
#   http://agentic-ai-staging-kdb-agent.staging.local:8001
#   http://agentic-ai-staging-portfolio-agent.staging.local:8004
#
# The api-service uses these URLs (configured via env vars in ecs.tf) to call
# agents over A2A (HTTP POST /a2a) without leaving the VPC.
# ─────────────────────────────────────────────────────────────────────────────

# ── Private DNS Namespace ─────────────────────────────────────────────────────

resource "aws_service_discovery_private_dns_namespace" "agents" {
  name        = "${var.environment}.local"
  description = "Private DNS namespace for A2A agent service discovery"
  vpc         = aws_vpc.main.id

  tags = { Name = "${local.name_prefix}-agents-ns" }
}

# ── Service Discovery Services (one per agent) ────────────────────────────────

resource "aws_service_discovery_service" "kdb_agent" {
  name = "${local.name_prefix}-kdb-agent"

  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.agents.id
    routing_policy = "MULTIVALUE"
    dns_records {
      ttl  = 10
      type = "A"
    }
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_service_discovery_service" "amps_agent" {
  name = "${local.name_prefix}-amps-agent"

  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.agents.id
    routing_policy = "MULTIVALUE"
    dns_records {
      ttl  = 10
      type = "A"
    }
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_service_discovery_service" "financial_orchestrator" {
  name = "${local.name_prefix}-financial-orchestrator"

  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.agents.id
    routing_policy = "MULTIVALUE"
    dns_records {
      ttl  = 10
      type = "A"
    }
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_service_discovery_service" "portfolio_agent" {
  name = "${local.name_prefix}-portfolio-agent"

  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.agents.id
    routing_policy = "MULTIVALUE"
    dns_records {
      ttl  = 10
      type = "A"
    }
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_service_discovery_service" "cds_agent" {
  name = "${local.name_prefix}-cds-agent"

  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.agents.id
    routing_policy = "MULTIVALUE"
    dns_records {
      ttl  = 10
      type = "A"
    }
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_service_discovery_service" "etf_agent" {
  name = "${local.name_prefix}-etf-agent"

  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.agents.id
    routing_policy = "MULTIVALUE"
    dns_records {
      ttl  = 10
      type = "A"
    }
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_service_discovery_service" "risk_pnl_agent" {
  name = "${local.name_prefix}-risk-pnl-agent"

  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.agents.id
    routing_policy = "MULTIVALUE"
    dns_records {
      ttl  = 10
      type = "A"
    }
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}
