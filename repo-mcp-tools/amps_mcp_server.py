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

# ── AMPS helpers ───────────────────────────────────────────────────────────────

def _get_amps_client():
    """Create and return a connected AMPS client."""
    try:
        from AMPS import Client
    except ImportError:
        raise RuntimeError(
            "amps-python-client not installed. Run: pip install amps-python-client"
        )
    client = Client(AMPS_CLIENT_NAME)
    client.connect(AMPS_TCP_URL)
    client.logon()
    return client


def _fetch_admin(path: str) -> dict:
    """Fetch a JSON endpoint from the AMPS HTTP admin interface."""
    import urllib.request
    url = f"{AMPS_ADMIN_URL}{path}"
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
                "List all topics available on the AMPS server (/topics.json). "
                "Returns topic names, message types, SOW status, message counts, "
                "and throughput statistics."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="amps_subscribe",
            description=(
                "Subscribe to an AMPS topic and collect messages. "
                "Use this to get a sample of real-time messages flowing through a topic. "
                "Optionally filter messages using AMPS content filter syntax (e.g. /price > 100)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "AMPS topic name to subscribe to (e.g. 'positions', 'orders')",
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
                "Optionally filter results using AMPS content filter syntax."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "SOW-enabled AMPS topic to query (e.g. 'positions', 'orders')",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Optional content filter (e.g. '/quantity > 0'). Leave empty for all records.",
                        "default": "",
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
        data = await loop.run_in_executor(None, _fetch_admin, "/topics.json")
        return _format_json(data)

    if name == "amps_subscribe":
        return await loop.run_in_executor(
            None,
            _subscribe,
            args["topic"],
            args.get("filter", ""),
            int(args.get("max_messages", 10)),
        )

    if name == "amps_sow_query":
        return await loop.run_in_executor(
            None,
            _sow_query,
            args["topic"],
            args.get("filter", ""),
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

def _subscribe(topic: str, filter: str = "", max_messages: int = 10) -> str:
    """Subscribe to a topic and collect up to max_messages."""
    try:
        from AMPS import Client, Command
    except ImportError:
        return "Error: amps-python-client not installed. Run: pip install amps-python-client"

    messages = []
    client = None
    try:
        client = _get_amps_client()
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


def _sow_query(topic: str, filter: str = "") -> str:
    """Query State-of-World for a topic."""
    try:
        from AMPS import Client, Command
    except ImportError:
        return "Error: amps-python-client not installed. Run: pip install amps-python-client"

    records = []
    client = None
    try:
        client = _get_amps_client()
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
