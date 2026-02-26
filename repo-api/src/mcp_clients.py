"""
MCP client factory for external servers:

  - Brave Search  → web search en tiempo real  (requiere BRAVE_API_KEY)
  - Fetch         → descarga y convierte URLs a texto plano
  - Filesystem    → lectura de archivos locales (docs/)
  - AMPS          → pub/sub, SOW query, publish (requiere AMPS_ENABLED=true)
  - KDB           → Bond RFQ historical analytics (requiere KDB_ENABLED=true)

Usage:
    from src.mcp_clients import open_mcp_tools

    with open_mcp_tools() as tools:
        agent = Agent(tools=[*native_tools, *tools])
        agent("pregunta")

Each MCPClient is opened only when its required conditions are met:
  - Brave     : only if BRAVE_API_KEY is set in the environment.
  - Fetch     : always enabled (no API key needed).
  - Filesystem: always enabled; exposes MCP_FILESYSTEM_PATH (default: ./data).
  - AMPS      : only if AMPS_ENABLED=true in environment.
  - KDB       : only if KDB_ENABLED=true in environment.
                KDB_MODE=poc  → DuckDB + Parquet (no license needed).
                KDB_MODE=server → real KDB+ via PyKX (requires kx.com license).
"""
import os
import sys
from contextlib import contextmanager, ExitStack

# Resolve the directory containing the MCP server scripts.
# In Docker (build context = repo root): set MCP_SERVER_DIR=/app/src/mcp_server
# In local monorepo dev: defaults to <repo-root>/repo-mcp-tools/
_MCP_SERVER_DIR = os.environ.get("MCP_SERVER_DIR") or os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "repo-mcp-tools")
)

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


def _amps_client() -> MCPClient:
    """AMPS MCP – subscribe, SOW query, publish, and server info."""
    server_script = os.path.join(_MCP_SERVER_DIR, "amps_mcp_server.py")
    return MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command=sys.executable,
                args=[server_script],
                env={**os.environ},
            )
        )
    )


def _kdb_client() -> MCPClient:
    """KDB MCP – Bond RFQ historical analytics (DuckDB in poc mode, KDB+ in server mode)."""
    server_script = os.path.join(_MCP_SERVER_DIR, "kdb_mcp_server.py")
    return MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command=sys.executable,
                args=[server_script],
                env={**os.environ},
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
    import shutil
    clients: list[MCPClient] = []

    has_npx = shutil.which("npx") is not None
    has_uvx = shutil.which("uvx") is not None

    if not has_npx:
        print("[MCP] npx not found – Brave Search and Filesystem MCP servers disabled. Install Node.js to enable them.")

    if os.environ.get("BRAVE_API_KEY"):
        if has_npx:
            clients.append(_brave_client())
        # else: already warned above
    else:
        print("[MCP] Brave Search disabled – set BRAVE_API_KEY to enable.")

    if has_uvx:
        clients.append(_fetch_client())
    else:
        print("[MCP] uvx not found – Fetch MCP server disabled.")

    if has_npx:
        clients.append(_filesystem_client(docs_path))

    if os.environ.get("AMPS_ENABLED", "false").lower() == "true":
        clients.append(_amps_client())
    else:
        print("[MCP] AMPS disabled – set AMPS_ENABLED=true to enable.")

    if os.environ.get("KDB_ENABLED", "false").lower() == "true":
        clients.append(_kdb_client())
    else:
        kdb_mode = os.environ.get("KDB_MODE", "poc")
        print(f"[MCP] KDB disabled – set KDB_ENABLED=true to enable (KDB_MODE={kdb_mode}).")

    with ExitStack() as stack:

        all_tools: list = []
        for client in clients:
            stack.enter_context(client)
            all_tools.extend(client.list_tools_sync())

        print(f"[MCP] {len(all_tools)} external tools loaded from {len(clients)} servers.")
        yield all_tools


@contextmanager
def open_amps_tools():
    """Context manager that opens only the AMPS MCP client.
    Yields an empty list if AMPS_ENABLED is not set.
    """
    if os.environ.get("AMPS_ENABLED", "false").lower() != "true":
        print("[MCP] AMPS disabled – set AMPS_ENABLED=true to enable.")
        yield []
        return
    client = _amps_client()
    with client:
        tools = client.list_tools_sync()
        print(f"[MCP] AMPS: {len(tools)} tools loaded.")
        yield tools


@contextmanager
def open_kdb_tools():
    """Context manager that opens only the KDB MCP client.
    Yields an empty list if KDB_ENABLED is not set.
    """
    if os.environ.get("KDB_ENABLED", "false").lower() != "true":
        print("[MCP] KDB disabled – set KDB_ENABLED=true to enable.")
        yield []
        return
    client = _kdb_client()
    with client:
        tools = client.list_tools_sync()
        print(f"[MCP] KDB: {len(tools)} tools loaded.")
        yield tools


def _portfolio_client() -> MCPClient:
    """Portfolio MCP – portfolio holdings and exposure analytics."""
    server_script = os.path.join(_MCP_SERVER_DIR, "portfolio_mcp_server.py")
    return MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command=sys.executable,
                args=[server_script],
                env={**os.environ},
            )
        )
    )


def _cds_client() -> MCPClient:
    """CDS MCP – Credit Default Swap market data and term structures."""
    server_script = os.path.join(_MCP_SERVER_DIR, "cds_mcp_server.py")
    return MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command=sys.executable,
                args=[server_script],
                env={**os.environ},
            )
        )
    )


def _etf_client() -> MCPClient:
    """ETF MCP – NAV, AUM, flows, and basket composition analytics."""
    server_script = os.path.join(_MCP_SERVER_DIR, "etf_mcp_server.py")
    return MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command=sys.executable,
                args=[server_script],
                env={**os.environ},
            )
        )
    )


@contextmanager
def open_portfolio_tools():
    """Context manager that opens only the Portfolio MCP client.
    Controlled by PORTFOLIO_ENABLED env var (default: true).
    """
    if os.environ.get("PORTFOLIO_ENABLED", "true").lower() != "true":
        print("[MCP] Portfolio disabled – set PORTFOLIO_ENABLED=true to enable.")
        yield []
        return
    client = _portfolio_client()
    with client:
        tools = client.list_tools_sync()
        print(f"[MCP] Portfolio: {len(tools)} tools loaded.")
        yield tools


@contextmanager
def open_cds_tools():
    """Context manager that opens only the CDS MCP client.
    Controlled by CDS_ENABLED env var (default: true).
    """
    if os.environ.get("CDS_ENABLED", "true").lower() != "true":
        print("[MCP] CDS disabled – set CDS_ENABLED=true to enable.")
        yield []
        return
    client = _cds_client()
    with client:
        tools = client.list_tools_sync()
        print(f"[MCP] CDS: {len(tools)} tools loaded.")
        yield tools


@contextmanager
def open_etf_tools():
    """Context manager that opens only the ETF MCP client.
    Controlled by ETF_ENABLED env var (default: true).
    """
    if os.environ.get("ETF_ENABLED", "true").lower() != "true":
        print("[MCP] ETF disabled – set ETF_ENABLED=true to enable.")
        yield []
        return
    client = _etf_client()
    with client:
        tools = client.list_tools_sync()
        print(f"[MCP] ETF: {len(tools)} tools loaded.")
        yield tools
