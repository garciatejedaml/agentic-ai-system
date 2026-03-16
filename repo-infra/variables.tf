variable "aws_region" {
  description = "AWS region to deploy all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment: staging | production"
  type        = string
  default     = "staging"

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be 'staging' or 'production'."
  }
}

variable "app_name" {
  description = "Application name used as a prefix for resource names"
  type        = string
  default     = "agentic-ai"
}

# ── Network ───────────────────────────────────────────────────────────────────

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones to use (2 is enough for staging, 3 for production)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

# ── ECS ───────────────────────────────────────────────────────────────────────

variable "image_tag" {
  description = "Docker image tag to deploy (e.g. git sha). Set via TF_VAR_image_tag in CI/CD."
  type        = string
  default     = "latest"
}

variable "task_cpu" {
  description = "ECS task CPU units (1024 = 1 vCPU)"
  type        = number
  default     = 1024
}

variable "task_memory" {
  description = "ECS task memory in MiB"
  type        = number
  default     = 2048
}

variable "service_desired_count" {
  description = "Initial number of ECS tasks to run"
  type        = number
  default     = 1
}

variable "service_min_count" {
  description = "Minimum number of tasks for auto-scaling"
  type        = number
  default     = 1
}

variable "service_max_count" {
  description = "Maximum number of tasks for auto-scaling"
  type        = number
  default     = 4
}

# ── Application config ────────────────────────────────────────────────────────

variable "kdb_enabled" {
  description = "Enable KDB historical analytics (poc mode uses parquet bundled in image)"
  type        = string
  default     = "true"
}

variable "amps_enabled" {
  description = "Enable AMPS live data integration (requires AMPS server reachable)"
  type        = string
  default     = "false"
}

variable "skip_ingest" {
  description = "Skip RAG doc ingestion on container startup (set true after first run)"
  type        = string
  default     = "false"
}

variable "log_level" {
  description = "Uvicorn log level: debug | info | warning | error"
  type        = string
  default     = "info"
}

# ── Aurora ────────────────────────────────────────────────────────────────────

variable "aurora_min_capacity" {
  description = "Aurora Serverless v2 min ACUs (0.5 = cheapest, auto-pauses)"
  type        = number
  default     = 0.5
}

variable "aurora_max_capacity" {
  description = "Aurora Serverless v2 max ACUs"
  type        = number
  default     = 4
}

variable "aurora_deletion_protection" {
  description = "Enable deletion protection on the Aurora cluster"
  type        = bool
  default     = false # set true for production
}

# ── Phase 2: A2A Agent settings ───────────────────────────────────────────────

variable "amps_host" {
  description = "Hostname of the AMPS server reachable from ECS tasks"
  type        = string
  default     = "localhost"
}

variable "amps_tcp_port" {
  description = "TCP port of the AMPS server (JSON transport)"
  type        = number
  default     = 9007
}

# ── Phase 4: Cross-region failover ────────────────────────────────────────────

variable "cross_region_failover_enabled" {
  description = "Enable DynamoDB Global Tables replica + Route53 health check in secondary region"
  type        = bool
  default     = false
}

variable "secondary_region" {
  description = "Secondary AWS region for DynamoDB Global Tables replica"
  type        = string
  default     = "us-west-2"
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID (required when cross_region_failover_enabled=true)"
  type        = string
  default     = ""
}

variable "langfuse_host" {
  description = "Internal URL of the self-hosted Langfuse instance used for LLM tracing (e.g. http://langfuse-web:3000). Leave empty to disable observability."
  type        = string
  default     = ""
}
