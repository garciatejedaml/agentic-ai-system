"""
MCP HTTP/SSE Transport Helper

Runs any mcp.server.Server as an HTTP service using the SSE transport.
Used by all MCP servers when MCP_TRANSPORT=http.

Endpoints exposed:
  GET  /sse         — SSE stream (MCP protocol entry point for clients)
  POST /messages/   — MCP client → server messages
  GET  /health      — JSON health check (used by Docker healthcheck + gateway)

On startup:
  1. Calls mcp_registry_client.register_mcp_server() to announce this server
  2. Starts a daemon heartbeat thread to keep the DynamoDB TTL alive

Environment variables (set per-container in docker-compose):
  MCP_SERVER_ID   — unique registry key  (e.g. "amps-mcp")
  MCP_PORT        — HTTP listen port     (e.g. "9100")
  MCP_HOST_URL    — public base URL for self-registration
                    (e.g. "http://amps-mcp-http:9100")
                    Defaults to http://0.0.0.0:{MCP_PORT} for local dev.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from mcp_registry_client import deregister_mcp_server, register_mcp_server, start_heartbeat

logger = logging.getLogger(__name__)


def run_http_server(
    server: Server,
    server_id: str,
    tools: list[str],
    port: int | None = None,
) -> None:
    """
    Start the MCP HTTP/SSE server and block until process exits.

    Args:
        server:    The configured mcp.server.Server instance (with tools registered).
        server_id: Registry key (e.g. "amps-mcp"). Overridden by MCP_SERVER_ID env.
        tools:     List of tool names this server exposes (for registry metadata).
        port:      HTTP port. Overridden by MCP_PORT env.
    """
    server_id = os.getenv("MCP_SERVER_ID", server_id)
    port = int(os.getenv("MCP_PORT", str(port or 9100)))
    host_url = os.getenv("MCP_HOST_URL", f"http://0.0.0.0:{port}")

    # ── Build Starlette app ───────────────────────────────────────────────────
    sse_transport = SseServerTransport("/messages/")

    async def handle_sse(request: Request):
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({
            "status": "ok",
            "server_id": server_id,
            "tools": tools,
            "transport": "http/sse",
        })

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/health", endpoint=health),
            Mount("/messages/", app=sse_transport.handle_post_message),
        ]
    )

    # ── Register in DynamoDB before accepting traffic ─────────────────────────
    register_mcp_server(server_id, host_url, tools)
    start_heartbeat(server_id, host_url, tools)

    # ── Graceful shutdown: deregister ─────────────────────────────────────────
    import signal

    def _on_exit(*_: Any) -> None:
        deregister_mcp_server(server_id)

    signal.signal(signal.SIGTERM, _on_exit)
    signal.signal(signal.SIGINT, _on_exit)

    logger.info("[mcp_http] %s listening on port %d (registered as %s)", server_id, port, host_url)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
