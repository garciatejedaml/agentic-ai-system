# ── VPC Endpoints ─────────────────────────────────────────────────────────────
# Keeps traffic to AWS services inside the VPC — avoids NAT Gateway costs
# for high-volume calls (especially Bedrock runtime).
#
# Each Interface endpoint costs ~$0.01/hr per AZ (~$7/month per endpoint, per AZ).
# With 2 AZs and 6 interface endpoints = ~$84/month saved on NAT vs endpoint cost
# (depends on Bedrock call volume — break-even at ~100GB NAT data/month).
# For staging with low traffic, you can comment them all out and use NAT instead.

locals {
  # Private subnet IDs for endpoint attachment
  private_subnet_ids = aws_subnet.private[*].id

  # Security group allowing HTTPS from app tasks
  endpoint_sg_ids = [aws_security_group.app.id]
}

# ── Interface Endpoints (HTTPS/443) ──────────────────────────────────────────

# Bedrock Runtime — main cost saver (every LLM call goes through here)
resource "aws_vpc_endpoint" "bedrock_runtime" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${local.region}.bedrock-runtime"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = local.private_subnet_ids
  security_group_ids  = local.endpoint_sg_ids
  private_dns_enabled = true

  tags = { Name = "${local.name_prefix}-endpoint-bedrock-runtime" }
}

# Secrets Manager — inject secrets into ECS containers
resource "aws_vpc_endpoint" "secrets_manager" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${local.region}.secretsmanager"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = local.private_subnet_ids
  security_group_ids  = local.endpoint_sg_ids
  private_dns_enabled = true

  tags = { Name = "${local.name_prefix}-endpoint-secretsmanager" }
}

# ECR API — pull image metadata
resource "aws_vpc_endpoint" "ecr_api" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${local.region}.ecr.api"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = local.private_subnet_ids
  security_group_ids  = local.endpoint_sg_ids
  private_dns_enabled = true

  tags = { Name = "${local.name_prefix}-endpoint-ecr-api" }
}

# ECR DKR — pull image layers
resource "aws_vpc_endpoint" "ecr_dkr" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${local.region}.ecr.dkr"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = local.private_subnet_ids
  security_group_ids  = local.endpoint_sg_ids
  private_dns_enabled = true

  tags = { Name = "${local.name_prefix}-endpoint-ecr-dkr" }
}

# CloudWatch Logs — write container logs
resource "aws_vpc_endpoint" "cloudwatch_logs" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${local.region}.logs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = local.private_subnet_ids
  security_group_ids  = local.endpoint_sg_ids
  private_dns_enabled = true

  tags = { Name = "${local.name_prefix}-endpoint-cloudwatch-logs" }
}

# SQS — async job queue
resource "aws_vpc_endpoint" "sqs" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${local.region}.sqs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = local.private_subnet_ids
  security_group_ids  = local.endpoint_sg_ids
  private_dns_enabled = true

  tags = { Name = "${local.name_prefix}-endpoint-sqs" }
}

# ── Gateway Endpoints (free) ──────────────────────────────────────────────────

# S3 — ECR pulls image layers from S3 under the hood
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${local.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = aws_route_table.private[*].id

  tags = { Name = "${local.name_prefix}-endpoint-s3" }
}
