#!/usr/bin/env python3
"""
AMPS MCP Server

Exposes AMPS (60East Technologies) capabilities as MCP tools so Strands agents
can query and interact with an AMPS server.

Tools:
  - amps_server_info     → fetch /amps.json  (server status, version, uptime)
  - amps_list_topics     → fetch /topics.json (all topics with stats)
  - amps_subscribe       → subscribe to a topic and collect N messages
  - amps_sow_query       → State-of-World query (latest state per key)
  - amps_publish         → publish a JSON message to a topic

Configuration (from environment):
  AMPS_HOST         → AMPS server host (default: localhost)
  AMPS_PORT         → AMPS TCP port   (default: 9007)
  AMPS_ADMIN_PORT   → AMPS HTTP admin port (default: 8085)
  AMPS_CLIENT_NAME  → client name shown in AMPS admin (default: agentic-ai-system)

Usage (standalone test):
  python src/mcp_server/amps_mcp_server.py

Usage (via MCP client in mcp_clients.py):
  Spawned automatically as a subprocess when AMPS_ENABLED=true.
"""
import json
import os
import sys
import asyncio
import logging
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

AMPS_HOST = os.getenv("AMPS_HOST", "localhost")
AMPS_PORT = int(os.getenv("AMPS_PORT", "9007"))
AMPS_ADMIN_PORT = int(os.getenv("AMPS_ADMIN_PORT", "8085"))
AMPS_CLIENT_NAME = os.getenv("AMPS_CLIENT_NAME", "agentic-ai-system")

AMPS_TCP_URL = f"tcp://{AMPS_HOST}:{AMPS_PORT}/amps/json"
AMPS_ADMIN_URL = f"http://{AMPS_HOST}:{AMPS_ADMIN_PORT}"

# Per-topic routing: AMPS_TOPIC_ROUTE_<topic>=host:port
# Allows one amps-agent to cover multiple AMPS instances (one per product).
# Example: AMPS_TOPIC_ROUTE_portfolio_nav=host.docker.internal:9008
_TOPIC_ROUTES: dict[str, tuple[str, int]] = {}
for _k, _v in os.environ.items():
    if _k.startswith("AMPS_TOPIC_ROUTE_"):
        _topic = _k[len("AMPS_TOPIC_ROUTE_"):]
        _host, _, _port = _v.rpartition(":")
        _TOPIC_ROUTES[_topic] = (_host, int(_port) if _port else 9007)

# ── AMPS helpers ───────────────────────────────────────────────────────────────

def _get_amps_client(topic: str | None = None,
                     host: str | None = None,
                     port: int | None = None):
    """Create and return a connected AMPS client.

    Resolution order for host/port:
      1. Explicit host/port args (passed by LLM from RAG knowledge)
      2. Per-topic env-var routing (_TOPIC_ROUTES) — fallback when RAG is unavailable
      3. Default AMPS_HOST / AMPS_PORT
    """
    try:
        from AMPS import Client
    except ImportError:
        raise RuntimeError(
            "amps-python-client not installed. Run: pip install amps-python-client"
        )
    if host and port:
        tcp_url = f"tcp://{host}:{port}/amps/json"
        client_name = f"{AMPS_CLIENT_NAME}-{topic or 'explicit'}"
    elif topic and topic in _TOPIC_ROUTES:
        h, p = _TOPIC_ROUTES[topic]
        tcp_url = f"tcp://{h}:{p}/amps/json"
        client_name = f"{AMPS_CLIENT_NAME}-{topic}"
    else:
        tcp_url = AMPS_TCP_URL
        client_name = AMPS_CLIENT_NAME
    client = Client(client_name)
    client.connect(tcp_url)
    client.logon()
    return client


def _fetch_admin(path: str, admin_url: str | None = None) -> dict:
    """Fetch a JSON endpoint from the AMPS HTTP admin interface."""
    import urllib.request
    url = f"{admin_url or AMPS_ADMIN_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e), "url": url}


def _format_json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


# ── MCP Server ──────────────────────────────────────────────────────────────────

server = Server("amps-mcp-server")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="amps_server_info",
            description=(
                "Fetch AMPS server status from the admin HTTP interface (/amps.json). "
                "Returns server version, uptime, connected clients count, memory usage, "
                "and general health information."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="amps_list_topics",
            description=(
                "List all topics available on an AMPS server (/topics.json). "
                "Returns topic names, message types, SOW status, message counts, "
                "and throughput statistics. "
                "Use host/port to query a specific AMPS instance when the topic's "
                "connection info is not in the knowledge base."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "host": {
                        "type": "string",
                        "description": "AMPS server host to query (default: configured AMPS_HOST). "
                                       "Use this to discover topics on a specific instance.",
                    },
                    "admin_port": {
                        "type": "integer",
                        "description": "AMPS HTTP admin port (default: configured AMPS_ADMIN_PORT, usually 8085).",
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="amps_subscribe",
            description=(
                "Subscribe to an AMPS topic and collect messages. "
                "Use this to get a sample of real-time messages flowing through a topic. "
                "Optionally filter messages using AMPS content filter syntax (e.g. /price > 100). "
                "Provide host/port if the topic lives on a specific AMPS instance "
                "(look up connection info in the knowledge base first)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "AMPS topic name to subscribe to (e.g. 'positions', 'portfolio_nav')",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Optional AMPS content filter (e.g. '/symbol = \"AAPL\"'). Leave empty for all messages.",
                        "default": "",
                    },
                    "max_messages": {
                        "type": "integer",
                        "description": "Maximum number of messages to collect before returning (default: 10)",
                        "default": 10,
                    },
                    "host": {
                        "type": "string",
                        "description": "Override AMPS host for this call (from knowledge base or amps_list_topics discovery).",
                    },
                    "port": {
                        "type": "integer",
                        "description": "Override AMPS TCP port for this call.",
                    },
                },
                "required": ["topic"],
            },
        ),
        types.Tool(
            name="amps_sow_query",
            description=(
                "Query the AMPS State-of-World (SOW) for a topic. "
                "Returns the latest/current state of all records in the topic "
                "(like a snapshot of the current data). "
                "Optionally filter results using AMPS content filter syntax. "
                "IMPORTANT: First search the knowledge base for the topic's connection info "
                "(host and port). If not found, use amps_list_topics to discover available topics."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "SOW-enabled AMPS topic to query (e.g. 'positions', 'portfolio_nav', 'cds_spreads')",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Optional content filter (e.g. '/portfolio_id = \"HY_MAIN\"'). Leave empty for all records.",
                        "default": "",
                    },
                    "host": {
                        "type": "string",
                        "description": "AMPS host for this topic (from knowledge base). "
                                       "Example: 'host.docker.internal'. Leave empty to use env default or topic routing.",
                    },
                    "port": {
                        "type": "integer",
                        "description": "AMPS TCP port for this topic (from knowledge base). "
                                       "Example: 9008 for portfolio_nav, 9009 for cds_spreads, 9010 for etf_nav, 9011 for risk_metrics.",
                    },
                },
                "required": ["topic"],
            },
        ),
        types.Tool(
            name="amps_publish",
            description=(
                "Publish a JSON message to an AMPS topic. "
                "Use this to send test data or trigger events in the AMPS system."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "AMPS topic to publish to",
                    },
                    "data": {
                        "type": "string",
                        "description": "JSON string to publish as the message body (e.g. '{\"id\": 1, \"price\": 100.0}')",
                    },
                },
                "required": ["topic", "data"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        result = await _dispatch(name, arguments)
    except Exception as e:
        result = f"Error: {e}"

    return [types.TextContent(type="text", text=str(result))]


async def _dispatch(name: str, args: dict) -> str:
    loop = asyncio.get_event_loop()

    if name == "amps_server_info":
        data = await loop.run_in_executor(None, _fetch_admin, "/amps.json")
        return _format_json(data)

    if name == "amps_list_topics":
        host = args.get("host")
        admin_port = args.get("admin_port")
        if host or admin_port:
            admin_url = f"http://{host or AMPS_HOST}:{admin_port or AMPS_ADMIN_PORT}"
            data = await loop.run_in_executor(
                None, lambda: _fetch_admin("/topics.json", admin_url)
            )
        else:
            data = await loop.run_in_executor(None, _fetch_admin, "/topics.json")
        return _format_json(data)

    if name == "amps_subscribe":
        return await loop.run_in_executor(
            None,
            _subscribe,
            args["topic"],
            args.get("filter", ""),
            int(args.get("max_messages", 10)),
            args.get("host"),
            args.get("port"),
        )

    if name == "amps_sow_query":
        return await loop.run_in_executor(
            None,
            _sow_query,
            args["topic"],
            args.get("filter", ""),
            args.get("host"),
            args.get("port"),
        )

    if name == "amps_publish":
        return await loop.run_in_executor(
            None,
            _publish,
            args["topic"],
            args["data"],
        )

    return f"Unknown tool: {name}"


# ── AMPS tool implementations (synchronous, run in executor) ───────────────────

def _subscribe(topic: str, filter: str = "", max_messages: int = 10,
               host: str | None = None, port: int | None = None) -> str:
    """Subscribe to a topic and collect up to max_messages."""
    try:
        from AMPS import Client, Command
    except ImportError:
        return "Error: amps-python-client not installed. Run: pip install amps-python-client"

    messages = []
    client = None
    try:
        client = _get_amps_client(topic, host, port)
        cmd = Command("subscribe").set_topic(topic)
        if filter:
            cmd.set_filter(filter)

        for msg in client.execute(cmd):
            data = msg.get_data()
            if data:
                messages.append(json.loads(data) if data.startswith("{") else data)
            if len(messages) >= max_messages:
                break

        if not messages:
            return f"No messages received from topic '{topic}' (filter: '{filter or 'none'}')"

        return _format_json({
            "topic": topic,
            "filter": filter or None,
            "message_count": len(messages),
            "messages": messages,
        })
    except Exception as e:
        return f"Subscribe error on topic '{topic}': {e}"
    finally:
        if client:
            try:
                client.disconnect()
            except Exception:
                pass


def _sow_query(topic: str, filter: str = "",
               host: str | None = None, port: int | None = None) -> str:
    """Query State-of-World for a topic."""
    try:
        from AMPS import Client, Command
    except ImportError:
        return "Error: amps-python-client not installed. Run: pip install amps-python-client"

    records = []
    client = None
    try:
        client = _get_amps_client(topic, host, port)
        cmd = Command("sow").set_topic(topic)
        if filter:
            cmd.set_filter(filter)

        for msg in client.execute(cmd):
            data = msg.get_data()
            if data:
                records.append(json.loads(data) if data.startswith("{") else data)

        if not records:
            return f"SOW topic '{topic}' is empty or filter returned no results (filter: '{filter or 'none'}')"

        return _format_json({
            "topic": topic,
            "filter": filter or None,
            "record_count": len(records),
            "records": records,
        })
    except Exception as e:
        return f"SOW query error on topic '{topic}': {e}"
    finally:
        if client:
            try:
                client.disconnect()
            except Exception:
                pass


def _publish(topic: str, data: str) -> str:
    """Publish a message to a topic."""
    try:
        from AMPS import Client
    except ImportError:
        return "Error: amps-python-client not installed. Run: pip install amps-python-client"

    client = None
    try:
        # Validate JSON
        parsed = json.loads(data)
        client = _get_amps_client()
        client.publish(topic, json.dumps(parsed))
        return f"Published to topic '{topic}': {data}"
    except json.JSONDecodeError as e:
        return f"Invalid JSON data: {e}"
    except Exception as e:
        return f"Publish error on topic '{topic}': {e}"
    finally:
        if client:
            try:
                client.disconnect()
            except Exception:
                pass


# ── Entry point ────────────────────────────────────────────────────────────────

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    asyncio.run(main())
