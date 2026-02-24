# ── LocalStack provider override ──────────────────────────────────────────────
# This file is ONLY used when running Terraform against LocalStack.
# The recommended approach is to use `tflocal` (pip install terraform-local)
# which auto-applies this configuration.
#
# Manual usage (without tflocal):
#   terraform init   -var-file=localstack.tfvars
#   terraform plan   -var-file=localstack.tfvars
#   terraform apply  -var-file=localstack.tfvars -auto-approve
#
# With tflocal (simpler — auto-patches endpoints):
#   pip install terraform-local
#   tflocal init
#   tflocal plan  -var-file=localstack.tfvars
#   tflocal apply -var-file=localstack.tfvars -auto-approve
#
# NOTE: rename this file to localstack_override.tf.disabled to exclude it
# when deploying to real AWS. The `tflocal` approach is cleaner since it
# doesn't require this file at all.

# Uncomment the block below only if NOT using tflocal:

# provider "aws" {
#   region                      = "us-east-1"
#   access_key                  = "test"
#   secret_key                  = "test"
#   skip_credentials_validation = true
#   skip_metadata_api_check     = true
#   skip_requesting_account_id  = true
#
#   endpoints {
#     sqs            = "http://localhost:4566"
#     dynamodb       = "http://localhost:4566"
#     secretsmanager = "http://localhost:4566"
#     s3             = "http://localhost:4566"
#     cloudwatchlogs = "http://localhost:4566"
#     iam            = "http://localhost:4566"
#     ecr            = "http://localhost:4566"
#     ecs            = "http://localhost:4566"
#     rds            = "http://localhost:4566"
#     sqs            = "http://localhost:4566"
#     elbv2          = "http://localhost:4566"
#     autoscaling    = "http://localhost:4566"
#   }
# }
