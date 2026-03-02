# ── Phase 4: Cross-Region Failover ────────────────────────────────────────────
#
# Enabled only when cross_region_failover_enabled=true (default: false).
#
# Session memory backup strategy:
#   • DynamoDB Global Tables (sessions + agent_registry) replicate automatically
#     to var.secondary_region — no code changes needed; same table name, same API.
#   • AMPS already provides its own cross-region failover via URL routing —
#     no additional infrastructure needed here.
#   • OpenSearch: point-in-time snapshots via automated S3 backup (manual restore).
#
# This file adds:
#   1. Route53 health check on the primary ALB (HTTP /health)
#   2. Output exposing the health check ID for CI/CD and external monitoring
#
# To activate secondary region ECS cluster (future):
#   Add a separate Terraform workspace or module targeting var.secondary_region
#   with the same task definitions and agent_common_env.

# ── Route53 Health Check (primary region ALB) ──────────────────────────────────

resource "aws_route53_health_check" "primary" {
  count = var.cross_region_failover_enabled ? 1 : 0

  fqdn              = aws_lb.api.dns_name
  port              = 80
  type              = "HTTP"
  resource_path     = "/health"
  failure_threshold = 3
  request_interval  = 10  # seconds between health checks

  tags = {
    Name        = "${local.name_prefix}-primary-health-check"
    Environment = var.environment
  }
}

# ── Outputs ────────────────────────────────────────────────────────────────────

output "health_check_id" {
  description = "Route53 health check ID for the primary ALB (null when failover disabled)"
  value       = var.cross_region_failover_enabled ? aws_route53_health_check.primary[0].id : null
}

output "health_check_url" {
  description = "URL being monitored by the Route53 health check"
  value       = var.cross_region_failover_enabled ? "http://${aws_lb.api.dns_name}/health" : null
}

output "cross_region_summary" {
  description = "Cross-region failover configuration summary"
  value = {
    enabled          = var.cross_region_failover_enabled
    primary_region   = local.region
    secondary_region = var.secondary_region
    replicated_tables = var.cross_region_failover_enabled ? [
      "${local.name_prefix}-sessions",
      "${local.name_prefix}-agent-registry",
    ] : []
    amps_note = "AMPS cross-region failover is handled automatically at the URL routing level"
  }
}
