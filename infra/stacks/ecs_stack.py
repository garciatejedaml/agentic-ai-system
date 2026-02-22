"""
EcsStack — ECS Fargate cluster, services, and task definitions.

Services (always-on):
  langgraph-api   → LangGraph FastAPI (OpenAI-compatible endpoint)
                    ALB-facing, port 8000
                    Auto-scales 1–4 tasks based on CPU utilization

Architecture notes:
  - MCP servers (AMPS, KDB) run as SUBPROCESSES inside the API container
    (stdio mode — same as local dev). This is simpler for the POC/V1.
  - For V2 multi-tenant platform: extract each MCP server to its own Fargate
    service and switch from stdio MCPClient to HTTP+SSE MCPClient.
  - Strands agents run in the same process as the API for now.
    For V2: extract to separate Fargate tasks dispatched via SQS.

Image:
  The image tag is read from the CDK_IMAGE_TAG env var (default: "latest").
  In CI/CD: set CDK_IMAGE_TAG=$(git rev-parse --short HEAD) before cdk deploy.

Bedrock:
  LLM_PROVIDER=bedrock tells model_factory.py to use BedrockModel instead of
  the Anthropic API. No API key needed — authentication is via the task_role IAM role.
"""
import os
import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_logs as logs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_secretsmanager as secretsmanager,
    aws_sqs as sqs,
    aws_applicationautoscaling as autoscaling,
)
from constructs import Construct


class EcsStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        ecr_repos: dict[str, ecr.Repository],
        task_role: iam.Role,
        execution_role: iam.Role,
        secret: secretsmanager.Secret,
        job_queue: sqs.Queue,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        image_tag = os.getenv("CDK_IMAGE_TAG", "latest")

        # ── ECS Cluster ────────────────────────────────────────────────────────
        self.cluster = ecs.Cluster(
            self, "Cluster",
            cluster_name="agentic-ai",
            vpc=vpc,
            container_insights=True,
        )

        # ── CloudWatch Log Group ───────────────────────────────────────────────
        log_group = logs.LogGroup(
            self, "AppLogs",
            log_group_name="/agentic-ai/api",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # ── Task Definition ────────────────────────────────────────────────────
        task_def = ecs.FargateTaskDefinition(
            self, "ApiTaskDef",
            family="agentic-ai-api",
            cpu=1024,          # 1 vCPU  — increase to 2048 if Strands agents are slow
            memory_limit_mib=2048,   # 2 GB  — Strands + LangGraph + ChromaDB in-process
            task_role=task_role,
            execution_role=execution_role,
        )

        # ── Container ──────────────────────────────────────────────────────────
        container = task_def.add_container(
            "api",
            image=ecs.ContainerImage.from_ecr_repository(
                ecr_repos["agentic-ai-api"],
                tag=image_tag,
            ),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="api",
                log_group=log_group,
            ),
            environment={
                # Use Bedrock in production — no API key needed (IAM auth via task_role)
                "LLM_PROVIDER":       "bedrock",
                "AWS_DEFAULT_REGION": self.region,
                # Model IDs (Bedrock cross-region inference profiles)
                "BEDROCK_MODEL":      "us.anthropic.claude-sonnet-4-6-20251101-v1:0",
                "ANTHROPIC_FAST_MODEL": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
                # RAG
                "CHROMA_PERSIST_DIR": "/data/chroma_db",
                "KDB_DATA_PATH":      "/app/data/kdb",
                "KDB_ENABLED":        "true",
                "KDB_MODE":           "poc",
                # Disable AMPS by default (requires AMPS server separately)
                "AMPS_ENABLED":       "false",
                # Observability (enable once Langfuse/Phoenix are deployed)
                "OBSERVABILITY_ENABLED": "false",
                # Server
                "PORT":               "8000",
                "UVICORN_WORKERS":    "2",
                "LOG_LEVEL":          "info",
                # Skip doc re-ingestion on every cold start after first run
                "SKIP_INGEST":        "false",
            },
            secrets={
                # These are injected at runtime from Secrets Manager
                # Value is the full JSON key path: secretsmanager:arn:field
                "BRAVE_API_KEY":        ecs.Secret.from_secrets_manager(secret, "BRAVE_API_KEY"),
                "LANGFUSE_PUBLIC_KEY":  ecs.Secret.from_secrets_manager(secret, "LANGFUSE_PUBLIC_KEY"),
                "LANGFUSE_SECRET_KEY":  ecs.Secret.from_secrets_manager(secret, "LANGFUSE_SECRET_KEY"),
            },
            port_mappings=[
                ecs.PortMapping(container_port=8000, protocol=ecs.Protocol.TCP),
            ],
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8000/ || exit 1"],
                interval=cdk.Duration.seconds(30),
                timeout=cdk.Duration.seconds(10),
                retries=3,
                start_period=cdk.Duration.seconds(60),  # allow time for doc ingestion
            ),
        )

        # ── Security group for ECS tasks ──────────────────────────────────────
        app_sg = ec2.SecurityGroup.from_security_group_id(
            self, "ImportedAppSg",
            security_group_id=cdk.Fn.import_value("AppSgId") if False else
                # Fallback: create a permissive SG if not importing (when stacks deployed independently)
                ec2.SecurityGroup(self, "AppSgFallback", vpc=vpc, allow_all_outbound=True).security_group_id,
        )

        # ── Fargate Service ────────────────────────────────────────────────────
        self.service = ecs.FargateService(
            self, "ApiService",
            service_name="agentic-ai-api",
            cluster=self.cluster,
            task_definition=task_def,
            desired_count=1,
            min_healthy_percent=100,
            max_healthy_percent=200,
            assign_public_ip=False,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
        )

        # ── Application Load Balancer ──────────────────────────────────────────
        alb = elbv2.ApplicationLoadBalancer(
            self, "Alb",
            load_balancer_name="agentic-ai-alb",
            vpc=vpc,
            internet_facing=True,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        listener = alb.add_listener(
            "HttpListener",
            port=80,
            open=True,
        )

        target_group = listener.add_targets(
            "ApiTarget",
            port=8000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[self.service],
            health_check=elbv2.HealthCheck(
                path="/",
                interval=cdk.Duration.seconds(30),
                timeout=cdk.Duration.seconds(10),
                healthy_http_codes="200",
            ),
            deregistration_delay=cdk.Duration.seconds(30),
        )

        # ── Auto-scaling ───────────────────────────────────────────────────────
        scaling = self.service.auto_scale_task_count(
            min_capacity=1,
            max_capacity=4,
        )
        scaling.scale_on_cpu_utilization(
            "ScaleOnCpu",
            target_utilization_percent=70,
            scale_in_cooldown=cdk.Duration.minutes(5),
            scale_out_cooldown=cdk.Duration.seconds(60),
        )

        # ── Outputs ────────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "AlbDnsName",    value=alb.load_balancer_dns_name)
        cdk.CfnOutput(self, "ApiEndpoint",   value=f"http://{alb.load_balancer_dns_name}/v1/chat/completions")
        cdk.CfnOutput(self, "ClusterName",   value=self.cluster.cluster_name)
        cdk.CfnOutput(self, "ServiceName",   value=self.service.service_name)
