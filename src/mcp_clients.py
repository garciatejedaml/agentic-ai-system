"""
MCP client factory for three external servers:

  - Brave Search  → web search en tiempo real  (requiere BRAVE_API_KEY)
  - Fetch         → descarga y convierte URLs a texto plano
  - Filesystem    → lectura de archivos locales (docs/)

Usage:
    from src.mcp_clients import open_mcp_tools

    with open_mcp_tools() as tools:
        agent = Agent(tools=[*native_tools, *tools])
        agent("pregunta")

Each MCPClient is opened only when its required conditions are met:
  - Brave  : only if BRAVE_API_KEY is set in the environment.
  - Fetch  : always enabled (no API key needed).
  - Filesystem: always enabled; exposes MCP_FILESYSTEM_PATH (default: ./data).
"""
import os
from contextlib import contextmanager, ExitStack

from mcp import StdioServerParameters, stdio_client
from strands.tools.mcp import MCPClient


def _brave_client() -> MCPClient:
    """Brave Search MCP – real-time web search."""
    return MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-brave-search"],
                env={**os.environ, "BRAVE_API_KEY": os.environ["BRAVE_API_KEY"]},
            )
        )
    )


def _fetch_client() -> MCPClient:
    """Fetch MCP – fetches any URL and returns clean markdown text."""
    return MCPClient(
        lambda: stdio_client(StdioServerParameters(command="uvx", args=["mcp-server-fetch"]))
    )


def _filesystem_client(path: str) -> MCPClient:
    """Filesystem MCP – read-only access to a local directory."""
    abs_path = os.path.abspath(path)
    return MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", abs_path],
            )
        )
    )


@contextmanager
def open_mcp_tools(docs_path: str = "./data"):
    """
    Context manager that opens all enabled MCP clients and yields
    a flat list of Strands-compatible tool objects.

    Args:
        docs_path: Local directory to expose via the Filesystem MCP server.
                   Defaults to './data'.

    Yields:
        list of tool objects ready to pass to a Strands Agent.
    """
    clients: list[MCPClient] = []

    if os.environ.get("BRAVE_API_KEY"):
        clients.append(_brave_client())
    else:
        print("[MCP] Brave Search disabled – set BRAVE_API_KEY to enable.")

    clients.append(_fetch_client())
    clients.append(_filesystem_client(docs_path))

    with ExitStack() as stack:
        all_tools: list = []
        for client in clients:
            stack.enter_context(client)
            all_tools.extend(client.list_tools_sync())

        print(f"[MCP] {len(all_tools)} external tools loaded from {len(clients)} servers.")
        yield all_tools
