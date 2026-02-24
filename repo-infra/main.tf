terraform {
  required_version = ">= 1.5"

  # ── Remote state (S3 + DynamoDB lock) ─────────────────────────────────────
  # Uncomment and fill in after creating the S3 bucket and DynamoDB table:
  #
  #   aws s3 mb s3://YOUR-BUCKET-NAME --region us-east-1
  #   aws dynamodb create-table \
  #     --table-name terraform-state-lock \
  #     --attribute-definitions AttributeName=LockID,AttributeType=S \
  #     --key-schema AttributeName=LockID,KeyType=HASH \
  #     --billing-mode PAY_PER_REQUEST \
  #     --region us-east-1
  #
  # backend "s3" {
  #   bucket         = "YOUR-BUCKET-NAME"
  #   key            = "agentic-ai-system/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "terraform-state-lock"
  #   encrypt        = true
  # }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "agentic-ai-system"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# ── Data sources ──────────────────────────────────────────────────────────────

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
