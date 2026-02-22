"""
NetworkStack — VPC, subnets, and security groups.

Topology:
  - 2 Availability Zones
  - Public subnets   → ALB only
  - Private subnets  → ECS tasks (NAT Gateway for outbound to Bedrock / external APIs)
  - Isolated subnets → Aurora Serverless v2 (no internet access)

Security groups:
  alb_sg     → allows 80/443 from internet
  app_sg     → allows 8000 from alb_sg only; allows all outbound (Bedrock HTTPS)
  data_sg    → allows 5432 from app_sg only
"""
import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from constructs import Construct


class NetworkStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── VPC ───────────────────────────────────────────────────────────────
        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=1,   # 1 NAT is enough for non-critical staging; use 2 for prod
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=28,
                ),
            ],
        )

        # ── Security groups ───────────────────────────────────────────────────

        # ALB: internet-facing (80 + 443)
        self.alb_sg = ec2.SecurityGroup(
            self, "AlbSg",
            vpc=self.vpc,
            description="ALB — allow HTTP/HTTPS from internet",
            allow_all_outbound=True,
        )
        self.alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80),  "HTTP")
        self.alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "HTTPS")

        # App (ECS tasks): only reachable from ALB or other app tasks
        self.app_sg = ec2.SecurityGroup(
            self, "AppSg",
            vpc=self.vpc,
            description="ECS tasks — allow 8000 from ALB",
            allow_all_outbound=True,  # needs to reach Bedrock, Brave, etc.
        )
        self.app_sg.add_ingress_rule(self.alb_sg, ec2.Port.tcp(8000), "API from ALB")
        # Allow internal agent-to-agent calls (MCP HTTP, future A2A protocol)
        self.app_sg.add_ingress_rule(self.app_sg, ec2.Port.tcp_range(5000, 5100), "Internal MCP HTTP")

        # Data (Aurora): only from ECS tasks
        self.data_sg = ec2.SecurityGroup(
            self, "DataSg",
            vpc=self.vpc,
            description="Aurora Serverless — allow 5432 from ECS tasks only",
            allow_all_outbound=False,
        )
        self.data_sg.add_ingress_rule(self.app_sg, ec2.Port.tcp(5432), "Postgres from ECS")

        # ── VPC Endpoints (avoid NAT costs for AWS services) ─────────────────
        # Bedrock runtime — high-volume, save NAT egress cost
        self.vpc.add_interface_endpoint(
            "BedrockEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService("bedrock-runtime"),
        )
        # Secrets Manager
        self.vpc.add_interface_endpoint(
            "SecretsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
        )
        # ECR (pull images without NAT)
        self.vpc.add_interface_endpoint(
            "EcrApiEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR,
        )
        self.vpc.add_interface_endpoint(
            "EcrDkrEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
        )
        # S3 gateway (ECR layers + general use)
        self.vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )
        # CloudWatch logs
        self.vpc.add_interface_endpoint(
            "CwLogsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
        )
        # SQS
        self.vpc.add_interface_endpoint(
            "SqsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SQS,
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "VpcId",  value=self.vpc.vpc_id)
        cdk.CfnOutput(self, "AlbSgId", value=self.alb_sg.security_group_id)
        cdk.CfnOutput(self, "AppSgId", value=self.app_sg.security_group_id)
