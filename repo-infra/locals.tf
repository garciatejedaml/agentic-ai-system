locals {
  name_prefix = "${var.app_name}-${var.environment}"

  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name

  # Bedrock model IDs (cross-region inference profiles)
  bedrock_model_sonnet = "us.anthropic.claude-sonnet-4-6-20251101-v1:0"
  bedrock_model_haiku  = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

  # ECR image URIs
  ecr_api_image = "${local.account_id}.dkr.ecr.${local.region}.amazonaws.com/${local.name_prefix}-api:${var.image_tag}"

  # Subnet CIDRs derived from VPC CIDR
  public_subnet_cidrs   = [cidrsubnet(var.vpc_cidr, 8, 0), cidrsubnet(var.vpc_cidr, 8, 1)]
  private_subnet_cidrs  = [cidrsubnet(var.vpc_cidr, 8, 10), cidrsubnet(var.vpc_cidr, 8, 11)]
  isolated_subnet_cidrs = [cidrsubnet(var.vpc_cidr, 12, 48), cidrsubnet(var.vpc_cidr, 12, 49)]
}
