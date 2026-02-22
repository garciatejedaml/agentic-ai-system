"""
EcrStack — ECR repositories for each container image.

Repositories:
  agentic-ai-api       → LangGraph FastAPI + all Strands agents (main image)

Future repositories (add when splitting into separate services):
  agentic-ai-amps-mcp  → AMPS MCP server (HTTP transport for inter-container)
  agentic-ai-kdb-mcp   → KDB MCP server (HTTP transport for inter-container)

Image lifecycle:
  - Keep last 5 tagged releases
  - Untagged (intermediate build layers) expire after 7 days
"""
import aws_cdk as cdk
from aws_cdk import aws_ecr as ecr
from constructs import Construct


class EcrStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.repos: dict[str, ecr.Repository] = {}

        for name in [
            "agentic-ai-api",
            # "agentic-ai-amps-mcp",  # uncomment when splitting MCP servers
            # "agentic-ai-kdb-mcp",
        ]:
            repo = ecr.Repository(
                self,
                name.replace("-", "_").title().replace("_", ""),
                repository_name=name,
                removal_policy=cdk.RemovalPolicy.RETAIN,  # don't delete images on stack destroy
                lifecycle_rules=[
                    ecr.LifecycleRule(
                        description="Keep last 5 tagged releases",
                        tag_status=ecr.TagStatus.TAGGED,
                        max_image_count=5,
                    ),
                    ecr.LifecycleRule(
                        description="Expire untagged layers after 7 days",
                        tag_status=ecr.TagStatus.UNTAGGED,
                        max_image_age=cdk.Duration.days(7),
                    ),
                ],
            )
            self.repos[name] = repo
            cdk.CfnOutput(self, f"{name}-Uri", value=repo.repository_uri)
