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
