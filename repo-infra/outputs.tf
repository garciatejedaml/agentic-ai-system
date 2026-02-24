# ── Networking ────────────────────────────────────────────────────────────────
output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

# ── ECR ───────────────────────────────────────────────────────────────────────
output "ecr_api_repository_url" {
  description = "ECR URL for the API image — use this in docker push"
  value       = aws_ecr_repository.api.repository_url
}

# ── ECS ───────────────────────────────────────────────────────────────────────
output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.api.name
}

# ── ALB ───────────────────────────────────────────────────────────────────────
output "alb_dns_name" {
  description = "ALB DNS — use for curl tests or point a CNAME at this"
  value       = aws_lb.api.dns_name
}

output "api_endpoint" {
  description = "OpenAI-compatible API endpoint"
  value       = "http://${aws_lb.api.dns_name}/v1/chat/completions"
}

# ── Data layer ────────────────────────────────────────────────────────────────
output "aurora_endpoint" {
  description = "Aurora cluster writer endpoint"
  value       = aws_rds_cluster.pgvector.endpoint
  sensitive   = true
}

output "agent_registry_table_name" {
  description = "DynamoDB agent registry table name"
  value       = aws_dynamodb_table.agent_registry.name
}

output "job_queue_url" {
  description = "SQS job queue URL"
  value       = aws_sqs_queue.jobs.url
}

output "app_secret_arn" {
  description = "Secrets Manager ARN — run 'aws secretsmanager put-secret-value' to populate"
  value       = aws_secretsmanager_secret.app.arn
}

# ── IAM ───────────────────────────────────────────────────────────────────────
output "task_role_arn" {
  description = "ECS task role ARN (has Bedrock + SQS + DynamoDB permissions)"
  value       = aws_iam_role.ecs_task.arn
}

output "execution_role_arn" {
  description = "ECS execution role ARN (ECR pull + CloudWatch logs + Secrets injection)"
  value       = aws_iam_role.ecs_execution.arn
}
