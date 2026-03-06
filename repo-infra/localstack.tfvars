# ── Terraform variables for LocalStack (local testing) ────────────────────────
# Usage:
#   tflocal init
#   tflocal plan  -var-file=localstack.tfvars
#   tflocal apply -var-file=localstack.tfvars -auto-approve

aws_region  = "us-east-1"
environment = "staging"
app_name    = "agentic-ai"

availability_zones = ["us-east-1a", "us-east-1b"]

image_tag   = "latest"
task_cpu    = 256     # minimum — LocalStack doesn't enforce Fargate limits
task_memory = 512

service_desired_count = 1
service_min_count     = 1
service_max_count     = 2

kdb_enabled  = "true"
amps_enabled = "false"
skip_ingest  = "true"

aurora_min_capacity        = 0.5
aurora_max_capacity        = 4
aurora_deletion_protection = false
