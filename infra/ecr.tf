# ── ECR Repository ────────────────────────────────────────────────────────────

resource "aws_ecr_repository" "api" {
  name                 = "${local.name_prefix}-api"
  image_tag_mutability = "MUTABLE" # allow re-tagging (e.g. 'latest')

  image_scanning_configuration {
    scan_on_push = true # free basic scan, catches known CVEs on push
  }

  tags = { Name = "${local.name_prefix}-api" }
}

# ── Lifecycle policy ──────────────────────────────────────────────────────────
# Keep last 5 tagged releases; expire untagged layers after 7 days.

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 5 tagged images"
        selection = {
          tagStatus   = "tagged"
          tagPrefixList = ["v", "sha-"]
          countType   = "imageCountMoreThan"
          countNumber = 5
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Expire untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      }
    ]
  })
}
