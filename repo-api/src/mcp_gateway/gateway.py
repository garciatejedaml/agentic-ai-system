"""
MCP Gateway — FastAPI Application

Acts as both:
  • MCP server  — external clients (Claude Desktop, etc.) connect here
  • MCP client  — proxies tool calls to the appropriate backend MCP server

Architecture:
  Client → GET /sse → gateway opens SSE connections to all registered backends
                    → presents unified tool list (all backends combined)
  Client → call_tool("amps_sow_query", ...) → gateway routes to amps-mcp endpoint

Auth:
  Header: X-MCP-API-Key: {MCP_GATEWAY_API_KEY}
  Missing/wrong key → 401. Set MCP_GATEWAY_API_KEY="" to disable auth (dev only).

Endpoints:
  GET  /sse        — MCP SSE stream for clients
  POST /messages/  — MCP client messages
  GET  /health     — lists registered backends and tool count

Environment:
  MCP_GATEWAY_API_KEY  — API key for client auth (empty = no auth)
  MCP_REGISTRY_TABLE   — DynamoDB table name (passed through to registry.py)
  AWS_ENDPOINT_URL     — LocalStack endpoint for local dev
"""
from __future__ import annotations

import asyncio
import logging
import os

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp import types
from starlette.routing import Mount, Route

from src.mcp_gateway.registry import get_server_for_tool, list_healthy_servers

logger = logging.getLogger(__name__)

_GATEWAY_API_KEY = os.getenv("MCP_GATEWAY_API_KEY", "")

# ── Build the gateway MCP server ─────────────────────────────────────────────

gateway_server = Server("mcp-gateway")


@gateway_server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Aggregate tools from all healthy MCP backend servers."""
    servers = list_healthy_servers()
    if not servers:
        logger.warning("[mcp_gateway] No healthy backends — tool list is empty")
        return []

    all_tools: list[types.Tool] = []
    async with asyncio.TaskGroup() as tg:
        results: list[asyncio.Task] = []
        for srv in servers:
            results.append(tg.create_task(_fetch_tools(srv["endpoint"])))

    for task in results:
        try:
            all_tools.extend(task.result())
        except Exception as exc:
            logger.warning("[mcp_gateway] list_tools partial failure: %s", exc)

    return all_tools


async def _fetch_tools(endpoint: str) -> list[types.Tool]:
    """Connect to a backend MCP server and list its tools."""
    try:
        async with sse_client(f"{endpoint}/sse") as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return result.tools
    except Exception as exc:
        logger.warning("[mcp_gateway] Could not fetch tools from %s: %s", endpoint, exc)
        return []


@gateway_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Route a tool call to the backend that owns that tool."""
    endpoint = get_server_for_tool(name)
    if not endpoint:
        return [types.TextContent(type="text", text=f"Tool '{name}' not found in any registered MCP server.")]

    try:
        async with sse_client(f"{endpoint}/sse") as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                return result.content
    except Exception as exc:
        logger.error("[mcp_gateway] Tool call '%s' failed on %s: %s", name, endpoint, exc)
        return [types.TextContent(type="text", text=f"Error calling '{name}': {exc}")]


# ── FastAPI app ───────────────────────────────────────────────────────────────

def _check_auth(request: Request) -> bool:
    if not _GATEWAY_API_KEY:
        return True  # auth disabled
    return request.headers.get("X-MCP-API-Key") == _GATEWAY_API_KEY


sse_transport = SseServerTransport("/messages/")


async def handle_sse(request: Request):
    if not _check_auth(request):
        return Response(content="Unauthorized", status_code=401)
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as (read_stream, write_stream):
        await gateway_server.run(
            read_stream,
            write_stream,
            gateway_server.create_initialization_options(),
        )


async def health(_request: Request) -> JSONResponse:
    servers = list_healthy_servers()
    total_tools = sum(len(s["tools"]) for s in servers)
    return JSONResponse({
        "status": "ok",
        "service": "mcp-gateway",
        "registered_backends": len(servers),
        "total_tools": total_tools,
        "backends": [
            {"server_id": s["server_id"], "endpoint": s["endpoint"], "tools": s["tools"]}
            for s in servers
        ],
    })


app = FastAPI(title="MCP Gateway", version="1.0.0")
app.add_route("/sse", handle_sse)
app.add_route("/health", health)
app.mount("/messages/", app=sse_transport.handle_post_message)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("MCP_GATEWAY_PORT", "9000"))
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
