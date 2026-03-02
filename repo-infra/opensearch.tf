# ── Amazon OpenSearch Service — RAG vector store ──────────────────────────────
#
# Replaces the local OpenSearch container used in dev.
# Single-node t3.small.search is cheap for staging; scale to m6g.large for prod.
#
# ECS tasks access OpenSearch via VPC endpoint (no public access).
# Fine-grained access control is disabled for simplicity; enable + add resource-based
# policy for production if your security team requires it.

# Security group: only ECS tasks can reach OpenSearch on port 443
resource "aws_security_group" "opensearch" {
  name        = "${local.name_prefix}-opensearch"
  description = "Allow ECS tasks to reach OpenSearch over HTTPS"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "HTTPS from ECS app SG"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name_prefix}-opensearch" }
}

resource "aws_opensearch_domain" "main" {
  domain_name    = "${local.name_prefix}-rag"
  engine_version = "OpenSearch_2.13"

  # ── Cluster ───────────────────────────────────────────────────────────────
  cluster_config {
    instance_type  = var.environment == "production" ? "m6g.large.search" : "t3.small.search"
    instance_count = var.environment == "production" ? 2 : 1

    # Multi-AZ only for production (t3.small doesn't support zone awareness)
    zone_awareness_enabled = var.environment == "production"

    dynamic "zone_awareness_config" {
      for_each = var.environment == "production" ? [1] : []
      content { availability_zone_count = 2 }
    }
  }

  # ── Storage ───────────────────────────────────────────────────────────────
  ebs_options {
    ebs_enabled = true
    volume_type = "gp3"
    volume_size = var.environment == "production" ? 50 : 20  # GB
  }

  # ── VPC placement ─────────────────────────────────────────────────────────
  vpc_options {
    subnet_ids         = var.environment == "production" ? aws_subnet.private[*].id : [aws_subnet.private[0].id]
    security_group_ids = [aws_security_group.opensearch.id]
  }

  # ── Encryption ────────────────────────────────────────────────────────────
  encrypt_at_rest { enabled = true }

  node_to_node_encryption { enabled = true }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  # ── Access policy: allow ECS task role to read/write ─────────────────────
  access_policies = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = aws_iam_role.ecs_task.arn }
      Action    = "es:*"
      Resource  = "arn:aws:es:${local.region}:${local.account_id}:domain/${local.name_prefix}-rag/*"
    }]
  })

  tags = { Name = "${local.name_prefix}-rag", Environment = var.environment }
}

# IAM: let ECS tasks call the OpenSearch domain
resource "aws_iam_role_policy" "ecs_task_opensearch" {
  name = "${local.name_prefix}-ecs-opensearch"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "OpenSearchRAG"
      Effect   = "Allow"
      Action   = ["es:ESHttpGet", "es:ESHttpPost", "es:ESHttpPut", "es:ESHttpDelete", "es:ESHttpHead"]
      Resource = "${aws_opensearch_domain.main.arn}/*"
    }]
  })
}

output "opensearch_endpoint" {
  description = "OpenSearch domain endpoint (used as OPENSEARCH_URL in ECS tasks)"
  value       = "https://${aws_opensearch_domain.main.endpoint}"
}
