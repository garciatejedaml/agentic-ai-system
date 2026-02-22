"""
DataStack — Persistent data layer.

Resources:
  Aurora Serverless v2 (PostgreSQL + pgvector)
    - Replaces ChromaDB for production RAG vector search
    - Auto-pauses when idle (cost-efficient for POC/staging)
    - Scales from 0.5 to 4 ACUs

  DynamoDB — Agent Registry (multi-tenant platform pattern)
    - Stores: agent_id, image_uri, keywords, mcp_endpoints, task_def_arn
    - Used by the orchestrator to discover registered specialist agents
    - Key schema: PK=agent_id (simple), GSI on desk_name for routing

  SQS — Async Job Queue
    - Decouples API layer from long-running agent runs
    - ECS tasks poll this queue to pick up work
    - DLQ for failed jobs (max 3 retries before going to dead-letter)

  Secrets Manager — App secrets bundle
    - Stores: ANTHROPIC_API_KEY, BRAVE_API_KEY, LANGFUSE keys
    - Injected as env vars into ECS task at runtime
    - Never hardcoded in image or CDK code
"""
import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_dynamodb as dynamodb,
    aws_sqs as sqs,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class DataStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Aurora Serverless v2 — pgvector ────────────────────────────────────
        # Used as production replacement for ChromaDB.
        # The application uses the pgvector extension for vector similarity search.
        # NOTE: To enable pgvector, run once after first deploy:
        #   CREATE EXTENSION IF NOT EXISTS vector;
        db_secret = rds.DatabaseSecret(
            self, "AuroraSecret",
            username="agenticai",
            secret_name="/agenticai/aurora/credentials",
        )
        self.aurora = rds.DatabaseCluster(
            self,
            "AuroraCluster",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_15_4
            ),
            default_database_name="agenticai",
            credentials=rds.Credentials.from_secret(db_secret),
            serverless_v2_min_capacity=0.5,
            serverless_v2_max_capacity=4,
            writer=rds.ClusterInstance.serverless_v2("writer"),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            storage_encrypted=True,
            deletion_protection=False,  # set True in production
        )

        # ── DynamoDB — Agent Registry ─────────────────────────────────────────
        # Enables the multi-tenant agent platform pattern.
        # Teams onboard their agents by writing a record to this table.
        # The orchestrator reads the table to discover which agents handle which keywords.
        self.agent_registry = dynamodb.Table(
            self,
            "AgentRegistry",
            table_name="agentic-ai-agent-registry",
            partition_key=dynamodb.Attribute(
                name="agent_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            point_in_time_recovery=True,
        )
        # GSI: query agents by desk name
        self.agent_registry.add_global_secondary_index(
            index_name="ByDesk",
            partition_key=dynamodb.Attribute(
                name="desk_name",
                type=dynamodb.AttributeType.STRING,
            ),
        )

        # ── SQS — Async Job Queue ─────────────────────────────────────────────
        # Agents that take >30s to run should be submitted here asynchronously.
        # The API returns a job_id immediately; client polls /v1/jobs/{id} for status.
        dlq = sqs.Queue(
            self,
            "AgentJobDLQ",
            queue_name="agentic-ai-jobs-dlq",
            retention_period=cdk.Duration.days(14),
        )
        self.job_queue = sqs.Queue(
            self,
            "AgentJobQueue",
            queue_name="agentic-ai-jobs",
            visibility_timeout=cdk.Duration.seconds(900),   # 15 min max agent run
            retention_period=cdk.Duration.hours(6),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=dlq,
            ),
        )

        # ── Secrets Manager — App secrets bundle ──────────────────────────────
        # Populate these values manually after first deploy:
        #   aws secretsmanager put-secret-value \
        #     --secret-id /agenticai/app/secrets \
        #     --secret-string '{"ANTHROPIC_API_KEY":"sk-ant-...","BRAVE_API_KEY":"..."}'
        self.app_secret = secretsmanager.Secret(
            self,
            "AppSecrets",
            secret_name="/agenticai/app/secrets",
            description="Runtime secrets for the Agentic AI System",
            # Placeholder — populate via CLI or console after deploy
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"ANTHROPIC_API_KEY":"REPLACE_ME","BRAVE_API_KEY":"REPLACE_ME","LANGFUSE_PUBLIC_KEY":"REPLACE_ME","LANGFUSE_SECRET_KEY":"REPLACE_ME"}',
                generate_string_key="dummy",  # required field, value unused
            ),
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "AuroraEndpoint",     value=self.aurora.cluster_endpoint.hostname)
        cdk.CfnOutput(self, "AgentRegistryName",  value=self.agent_registry.table_name)
        cdk.CfnOutput(self, "JobQueueUrl",        value=self.job_queue.queue_url)
        cdk.CfnOutput(self, "AppSecretArn",       value=self.app_secret.secret_arn)
