"""
A2A Agent Registry — DynamoDB backend

Agents register themselves on startup and deregister on shutdown.
The Financial Orchestrator discovers agents by agent_id at call time.

Table: agentic-ai-staging-agent-registry (already created by Terraform + LocalStack init)
  PK: agent_id (String)
  GSI ByDesk: desk_name (String)

Environment:
  AWS_ENDPOINT_URL  → set to http://localstack:4566 for local dev (empty = real AWS)
  AWS_DEFAULT_REGION → us-east-1
"""
import os
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError

_TABLE = os.getenv("AGENT_REGISTRY_TABLE", "agentic-ai-staging-agent-registry")
_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
_ENDPOINT = os.getenv("AWS_ENDPOINT_URL", "") or None  # None = real AWS

# TTL for registered agents (seconds). Healthcheck should renew before expiry.
_TTL_SECONDS = 120


def _table():
    kwargs = {"region_name": _REGION}
    if _ENDPOINT:
        kwargs["endpoint_url"] = _ENDPOINT
    dynamodb = boto3.resource("dynamodb", **kwargs)
    return dynamodb.Table(_TABLE)


def register_agent(
    agent_id: str,
    endpoint: str,
    capabilities: list[str],
    desk_names: list[str],
) -> None:
    """
    Register or refresh an agent in DynamoDB.

    Args:
        agent_id:     Unique identifier (e.g. "kdb-agent")
        endpoint:     Base URL of the agent (e.g. "http://kdb-agent:8001")
        capabilities: List of skill IDs
        desk_names:   Trading desks this agent serves (e.g. ["HY", "IG"])
    """
    try:
        _table().put_item(Item={
            "agent_id": agent_id,
            "desk_name": desk_names[0] if desk_names else "ALL",
            "endpoint": endpoint,
            "capabilities": capabilities,
            "desk_names": desk_names,
            "status": "healthy",
            "registered_at": int(time.time()),
            "ttl": int(time.time()) + _TTL_SECONDS,
        })
    except (ClientError, BotoCoreError, Exception) as e:
        print(f"[registry] WARNING: could not register {agent_id}: {e}")


def deregister_agent(agent_id: str) -> None:
    """Remove agent from registry (called on shutdown)."""
    try:
        _table().delete_item(Key={"agent_id": agent_id})
    except (ClientError, BotoCoreError, Exception) as e:
        print(f"[registry] WARNING: could not deregister {agent_id}: {e}")


def discover_agent(agent_id: str) -> dict | None:
    """
    Look up a specific agent by ID.

    Returns the item dict (with 'endpoint', 'capabilities', etc.)
    or None if not found.
    """
    try:
        resp = _table().get_item(Key={"agent_id": agent_id})
        return resp.get("Item")
    except (ClientError, BotoCoreError, Exception) as e:
        print(f"[registry] WARNING: could not discover {agent_id}: {e}")
        return None


def get_endpoint(agent_id: str, fallback: str) -> str:
    """
    Get the endpoint for an agent, falling back to a configured default.

    Used by the Financial Orchestrator to resolve agent URLs at call time.
    """
    item = discover_agent(agent_id)
    if item and item.get("status") == "healthy":
        return item["endpoint"]
    return fallback
