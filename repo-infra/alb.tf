# ── Application Load Balancer ─────────────────────────────────────────────────

resource "aws_lb" "api" {
  name               = "${local.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  # Enable access logs for debugging (optional — needs S3 bucket)
  # access_logs {
  #   bucket  = "my-alb-logs-bucket"
  #   enabled = true
  # }

  tags = { Name = "${local.name_prefix}-alb" }
}

# ── Target Group ──────────────────────────────────────────────────────────────

resource "aws_lb_target_group" "api" {
  name        = "${local.name_prefix}-api-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip" # required for Fargate awsvpc networking

  health_check {
    path                = "/"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    matcher             = "200"
  }

  deregistration_delay = 30 # drain connections fast during deploys

  tags = { Name = "${local.name_prefix}-api-tg" }
}

# ── Phase 2: Agent Target Groups ─────────────────────────────────────────────

resource "aws_lb_target_group" "kdb_agent" {
  name        = "${local.name_prefix}-kdb-tg"
  port        = 8001
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    matcher             = "200"
  }

  deregistration_delay = 30
  tags = { Name = "${local.name_prefix}-kdb-tg" }
}

resource "aws_lb_target_group" "amps_agent" {
  name        = "${local.name_prefix}-amps-tg"
  port        = 8002
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    matcher             = "200"
  }

  deregistration_delay = 30
  tags = { Name = "${local.name_prefix}-amps-tg" }
}

resource "aws_lb_target_group" "financial_orchestrator" {
  name        = "${local.name_prefix}-fin-tg"
  port        = 8003
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    matcher             = "200"
  }

  deregistration_delay = 30
  tags = { Name = "${local.name_prefix}-fin-tg" }
}

# ── Listener: HTTP (port 80) ──────────────────────────────────────────────────
# Forward all traffic to the API target group.
# For production: add an HTTPS listener (port 443) with an ACM certificate
# and redirect HTTP → HTTPS.

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# ── Phase 2: Listener Rules — route internal A2A calls to agent services ──────
# External traffic goes to the API service (default rule above).
# Agent-to-agent calls use the X-Agent-Service header for routing.
# In production these would be internal VPC calls, but the ALB rules
# allow traffic from other ECS tasks to reach specific agent services.

resource "aws_lb_listener_rule" "kdb_agent" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.kdb_agent.arn
  }

  condition {
    http_header {
      http_header_name = "X-Agent-Service"
      values           = ["kdb"]
    }
  }
}

resource "aws_lb_listener_rule" "amps_agent" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 20

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.amps_agent.arn
  }

  condition {
    http_header {
      http_header_name = "X-Agent-Service"
      values           = ["amps"]
    }
  }
}

resource "aws_lb_listener_rule" "financial_orchestrator" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 30

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.financial_orchestrator.arn
  }

  condition {
    http_header {
      http_header_name = "X-Agent-Service"
      values           = ["financial"]
    }
  }
}

# ── HTTPS Listener (production — uncomment when ACM cert is ready) ────────────
# resource "aws_lb_listener" "https" {
#   load_balancer_arn = aws_lb.api.arn
#   port              = 443
#   protocol          = "HTTPS"
#   ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
#   certificate_arn   = "arn:aws:acm:REGION:ACCOUNT:certificate/CERT-ID"
#
#   default_action {
#     type             = "forward"
#     target_group_arn = aws_lb_target_group.api.arn
#   }
# }
#
# resource "aws_lb_listener" "http_redirect" {
#   load_balancer_arn = aws_lb.api.arn
#   port              = 80
#   protocol          = "HTTP"
#   default_action {
#     type = "redirect"
#     redirect {
#       port        = "443"
#       protocol    = "HTTPS"
#       status_code = "HTTP_301"
#     }
#   }
# }
