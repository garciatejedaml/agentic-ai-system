"""
MCP Gateway — Registry Reader

Reads the DynamoDB mcp-registry table to discover healthy MCP HTTP servers.
The gateway calls list_healthy_servers() on each incoming connection to get
the current set of backends — no restart needed when a new MCP server deploys.

Table: MCP_REGISTRY_TABLE (default: agentic-ai-staging-mcp-registry)

Graceful degradation: returns empty list if DynamoDB unavailable.
"""
from __future__ import annotations

import logging
import os
import time

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_TABLE_NAME = os.getenv("MCP_REGISTRY_TABLE", "agentic-ai-staging-mcp-registry")
_dynamodb = None


def _get_table():
    global _dynamodb
    if _dynamodb is None:
        kwargs: dict = {"region_name": os.getenv("AWS_DEFAULT_REGION", "us-east-1")}
        endpoint = os.getenv("AWS_ENDPOINT_URL")
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        _dynamodb = boto3.resource("dynamodb", **kwargs).Table(_TABLE_NAME)
    return _dynamodb


def list_healthy_servers() -> list[dict]:
    """
    Return all currently healthy MCP servers from the registry.

    Each entry: {"server_id": str, "endpoint": str, "tools": list[str]}

    A server is healthy if:
      - status == "healthy"
      - ttl > now (not expired yet)
    """
    try:
        now = int(time.time())
        response = _get_table().scan()
        items = response.get("Items", [])
        healthy = []
        for item in items:
            if item.get("status") != "healthy":
                continue
            if int(item.get("ttl", 0)) < now:
                continue
            tools = list(item.get("tools", set()))
            # Remove internal placeholder used for empty sets
            tools = [t for t in tools if t != "__none__"]
            healthy.append({
                "server_id": item["server_id"],
                "endpoint":  item["endpoint"],
                "tools":     tools,
            })
        return healthy
    except Exception as exc:
        logger.warning("[mcp_gateway.registry] DynamoDB unavailable: %s", exc)
        return []


def get_server_for_tool(tool_name: str) -> str | None:
    """
    Return the endpoint of the server that exposes `tool_name`, or None.
    """
    for server in list_healthy_servers():
        if tool_name in server["tools"]:
            return server["endpoint"]
    return None
