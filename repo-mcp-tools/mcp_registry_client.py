"""
MCP Server Registry Client

Auto-registration helper for MCP HTTP servers. Each MCP server calls
register_mcp_server() on startup and start_heartbeat() to maintain its
entry in DynamoDB.

The MCP Gateway reads this table to discover healthy servers dynamically —
no manual gateway configuration needed when a new MCP server is deployed.

DynamoDB Table: MCP_REGISTRY_TABLE (default: agentic-ai-staging-mcp-registry)
  PK: server_id  (e.g. "amps-mcp", "kdb-mcp")
  Attributes:
    endpoint   (S)  — base HTTP URL  (e.g. "http://amps-mcp-http:9100")
    tools      (SS) — set of tool names exposed by this server
    status     (S)  — "healthy" | "unhealthy"
    registered_at (N) — Unix timestamp
    ttl        (N)  — auto-expire after 90s (servers heartbeat every 60s)

Graceful degradation: if DynamoDB unavailable, logs warning and continues.
The MCP server still works — the gateway just won't see it in auto-discovery.
"""
from __future__ import annotations

import logging
import os
import time
import threading

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_TABLE_NAME = os.getenv("MCP_REGISTRY_TABLE", "agentic-ai-staging-mcp-registry")
_TTL_SECONDS = 90  # gateway considers server dead after 90s without heartbeat
_HEARTBEAT_INTERVAL = 60  # seconds between re-registration

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


def register_mcp_server(server_id: str, endpoint: str, tools: list[str]) -> None:
    """
    Register or refresh this MCP server in the DynamoDB registry.

    Args:
        server_id: Unique identifier (e.g. "amps-mcp"). Set via MCP_SERVER_ID env.
        endpoint:  Full HTTP base URL of this server (e.g. "http://amps-mcp-http:9100").
        tools:     List of tool names this server exposes.
    """
    try:
        table = _get_table()
        table.put_item(Item={
            "server_id":     server_id,
            "endpoint":      endpoint,
            "tools":         set(tools) if tools else {"__none__"},
            "status":        "healthy",
            "registered_at": int(time.time()),
            "ttl":           int(time.time()) + _TTL_SECONDS,
        })
        logger.info("[mcp_registry] Registered %s → %s (%d tools)", server_id, endpoint, len(tools))
    except Exception as exc:
        logger.warning("[mcp_registry] DynamoDB unavailable — skipping registration: %s", exc)


def deregister_mcp_server(server_id: str) -> None:
    """Remove server from registry on graceful shutdown."""
    try:
        _get_table().delete_item(Key={"server_id": server_id})
        logger.info("[mcp_registry] Deregistered %s", server_id)
    except Exception as exc:
        logger.warning("[mcp_registry] Deregister failed (non-critical): %s", exc)


def start_heartbeat(
    server_id: str,
    endpoint: str,
    tools: list[str],
    interval: int = _HEARTBEAT_INTERVAL,
) -> threading.Thread:
    """
    Start a daemon thread that re-registers the server every `interval` seconds,
    keeping the DynamoDB TTL alive.

    Returns the thread (already started). Daemon — stops automatically when the
    main process exits.
    """
    def _loop():
        while True:
            time.sleep(interval)
            register_mcp_server(server_id, endpoint, tools)

    t = threading.Thread(target=_loop, daemon=True, name=f"mcp-heartbeat-{server_id}")
    t.start()
    logger.info("[mcp_registry] Heartbeat thread started for %s (every %ds)", server_id, interval)
    return t
