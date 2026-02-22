#!/usr/bin/env python3
"""
Agentic AI System — AWS CDK Application

Deploys the full agentic AI system to AWS using ECS Fargate + Bedrock.

Stacks:
  NetworkStack  → VPC, subnets, security groups
  EcrStack      → ECR repositories (one per container image)
  DataStack     → Aurora Serverless v2 (pgvector), DynamoDB registry, SQS, Secrets Manager
  IamStack      → IAM roles with Bedrock + ECS permissions
  EcsStack      → ECS cluster, Fargate services, ALB

Usage:
  cd infra
  pip install -r requirements.txt
  cdk bootstrap aws://ACCOUNT_ID/REGION
  cdk deploy --all

  # Or deploy stacks one at a time:
  cdk deploy AgenticAI-Network
  cdk deploy AgenticAI-ECR
  cdk deploy AgenticAI-Data
  cdk deploy AgenticAI-IAM
  cdk deploy AgenticAI-ECS

Environment variables (set before cdk deploy):
  CDK_DEFAULT_ACCOUNT   → your AWS account ID
  CDK_DEFAULT_REGION    → target region (default: us-east-1)
  APP_ENV               → "staging" | "production" (default: staging)
"""
import os
import aws_cdk as cdk

from stacks.network_stack import NetworkStack
from stacks.ecr_stack import EcrStack
from stacks.data_stack import DataStack
from stacks.iam_stack import IamStack
from stacks.ecs_stack import EcsStack

app = cdk.App()

env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT", os.getenv("AWS_ACCOUNT_ID")),
    region=os.getenv("CDK_DEFAULT_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1")),
)

app_env = os.getenv("APP_ENV", "staging")
prefix  = f"AgenticAI-{app_env.capitalize()}"

# ── Stack 1: Network ──────────────────────────────────────────────────────────
network = NetworkStack(app, f"{prefix}-Network", env=env)

# ── Stack 2: ECR repositories ─────────────────────────────────────────────────
ecr = EcrStack(app, f"{prefix}-ECR", env=env)

# ── Stack 3: Data layer ───────────────────────────────────────────────────────
data = DataStack(
    app,
    f"{prefix}-Data",
    vpc=network.vpc,
    env=env,
)

# ── Stack 4: IAM roles ────────────────────────────────────────────────────────
iam = IamStack(
    app,
    f"{prefix}-IAM",
    env=env,
)

# ── Stack 5: ECS cluster + services ──────────────────────────────────────────
ecs = EcsStack(
    app,
    f"{prefix}-ECS",
    vpc=network.vpc,
    ecr_repos=ecr.repos,
    task_role=iam.task_role,
    execution_role=iam.execution_role,
    secret=data.app_secret,
    job_queue=data.job_queue,
    env=env,
)

# Explicit dependency order
ecs.add_dependency(iam)
ecs.add_dependency(ecr)
ecs.add_dependency(data)

app.synth()
