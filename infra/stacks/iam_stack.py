"""
IamStack — IAM roles for ECS tasks.

Roles:
  task_role       → permissions granted TO the running container (what it can do)
  execution_role  → permissions for ECS control plane (pull image, write logs, get secrets)

task_role grants:
  - bedrock:InvokeModel  — call any Bedrock model in the region (Claude, Titan, etc.)
  - sqs:ReceiveMessage / DeleteMessage / SendMessage  — async job queue
  - dynamodb:GetItem / Query / Scan  — read agent registry
  - secretsmanager:GetSecretValue  — read own secret bundle
  - s3:GetObject  — read from data bucket (parquet files, etc.)

execution_role grants (standard ECS):
  - ecr:GetAuthorizationToken + ecr:BatchGetImage  — pull image from ECR
  - logs:CreateLogStream + logs:PutLogEvents  — write to CloudWatch
  - secretsmanager:GetSecretValue  — inject secrets as env vars
"""
import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from constructs import Construct


class IamStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Task Role (container permissions) ────────────────────────────────
        self.task_role = iam.Role(
            self,
            "EcsTaskRole",
            role_name="agentic-ai-ecs-task-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="Grants ECS tasks access to Bedrock, SQS, DynamoDB, Secrets",
        )

        # Bedrock: invoke any foundation model (Claude Haiku/Sonnet/Opus)
        self.task_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockInvoke",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=["*"],  # scope to specific model ARNs in production if desired
            )
        )

        # SQS: async job queue operations
        self.task_role.add_to_policy(
            iam.PolicyStatement(
                sid="SqsJobQueue",
                effect=iam.Effect.ALLOW,
                actions=[
                    "sqs:SendMessage",
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                ],
                resources=["*"],  # scope to queue ARN after DataStack deploy
            )
        )

        # DynamoDB: read agent registry
        self.task_role.add_to_policy(
            iam.PolicyStatement(
                sid="DynamoAgentRegistry",
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:Query",
                    "dynamodb:Scan",
                    "dynamodb:PutItem",   # for agent self-registration on startup
                ],
                resources=["*"],  # scope to table ARN after DataStack deploy
            )
        )

        # Secrets Manager: read app secrets at runtime
        self.task_role.add_to_policy(
            iam.PolicyStatement(
                sid="SecretsRead",
                effect=iam.Effect.ALLOW,
                actions=["secretsmanager:GetSecretValue"],
                resources=["*"],  # scope to /agenticai/* ARN after DataStack deploy
            )
        )

        # CloudWatch: custom metrics (optional, for LangGraph span publishing)
        self.task_role.add_to_policy(
            iam.PolicyStatement(
                sid="CloudWatchMetrics",
                effect=iam.Effect.ALLOW,
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
            )
        )

        # ── Execution Role (ECS control plane) ───────────────────────────────
        self.execution_role = iam.Role(
            self,
            "EcsExecutionRole",
            role_name="agentic-ai-ecs-execution-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                ),
            ],
        )

        # Allow execution role to read secrets for env var injection
        self.execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="SecretsForEnvInjection",
                effect=iam.Effect.ALLOW,
                actions=["secretsmanager:GetSecretValue"],
                resources=["*"],
            )
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "TaskRoleArn",      value=self.task_role.role_arn)
        cdk.CfnOutput(self, "ExecutionRoleArn", value=self.execution_role.role_arn)
