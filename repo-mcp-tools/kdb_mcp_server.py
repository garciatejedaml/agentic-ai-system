#!/usr/bin/env python3
"""
KDB MCP Server

Exposes Bond RFQ historical data as MCP tools for Strands agents.

Two backend modes (controlled by KDB_MODE env var):

  poc    → DuckDB reads Parquet files from KDB_DATA_PATH (default: ./data/kdb)
           No license needed. Run: python scripts/generate_synthetic_rfq.py first.

  server → PyKX connects to a running KDB+ server at KDB_HOST:KDB_PORT.
           Requires: pip install pykx + valid kc.lic license.
           Start server: docker compose -f docker-compose.kdb.yml up -d

Tools:
  - kdb_list_tables       → list available tables
  - kdb_get_schema        → column names and types for a table
  - kdb_query             → SQL (poc) or Q code (server) query
  - kdb_rfq_analytics     → high-level RFQ analytics (desk / trader / period)

Configuration (env vars):
  KDB_MODE        → "poc" (default) or "server"
  KDB_DATA_PATH   → path to Parquet files (poc mode, default: ./data/kdb)
  KDB_HOST        → KDB+ server host (server mode, default: localhost)
  KDB_PORT        → KDB+ server port (server mode, default: 5000)

Usage (standalone test):
  python src/mcp_server/kdb_mcp_server.py
"""
import json
import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

KDB_MODE = os.getenv("KDB_MODE", "poc").lower()          # "poc" | "server"
KDB_DATA_PATH = os.getenv("KDB_DATA_PATH", "./data/kdb")
KDB_HOST = os.getenv("KDB_HOST", "localhost")
KDB_PORT = int(os.getenv("KDB_PORT", "5000"))

# ── Backend initialisation ─────────────────────────────────────────────────────

def _init_poc_backend():
    """Load Parquet files into DuckDB in-memory database."""
    import duckdb
    conn = duckdb.connect(":memory:")
    data_dir = Path(KDB_DATA_PATH)
    loaded = []
    for pq in data_dir.glob("*.parquet"):
        table = pq.stem
        conn.execute(f"CREATE TABLE {table} AS SELECT * FROM read_parquet('{pq}')")
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        loaded.append((table, count))
        logger.info("[KDB-POC] Loaded %s: %d rows", table, count)
    if not loaded:
        logger.warning(
            "[KDB-POC] No Parquet files found in %s. "
            "Run: python scripts/generate_synthetic_rfq.py", KDB_DATA_PATH
        )
    return conn, loaded


def _init_server_backend():
    """Connect to a running KDB+ server via PyKX."""
    try:
        import pykx as kx
    except ImportError:
        raise RuntimeError("pykx not installed. Run: pip install pykx")
    conn = kx.QConnection(host=KDB_HOST, port=KDB_PORT)
    logger.info("[KDB-SERVER] Connected to KDB+ at %s:%d", KDB_HOST, KDB_PORT)
    return conn


# Lazy singletons
_poc_conn = None
_poc_tables: list[tuple[str, int]] = []
_server_conn = None


def _get_poc_conn():
    global _poc_conn, _poc_tables
    if _poc_conn is None:
        import duckdb
        _poc_conn, _poc_tables = _init_poc_backend()
    return _poc_conn


def _get_server_conn():
    global _server_conn
    if _server_conn is None:
        _server_conn = _init_server_backend()
    return _server_conn


# ── Tool helpers ───────────────────────────────────────────────────────────────

def _fmt(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _poc_list_tables() -> str:
    conn = _get_poc_conn()
    rows = conn.execute("SHOW TABLES").fetchall()
    tables = []
    for (name,) in rows:
        count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        tables.append({"table": name, "rows": count})
    return _fmt({"mode": "poc (DuckDB)", "tables": tables})


def _server_list_tables() -> str:
    conn = _get_server_conn()
    result = conn("tables[]")
    return _fmt({"mode": "server (KDB+)", "tables": list(result)})


def _poc_get_schema(table: str) -> str:
    conn = _get_poc_conn()
    try:
        rows = conn.execute(f"DESCRIBE {table}").fetchall()
        schema = [{"column": r[0], "type": r[1]} for r in rows]
        return _fmt({"table": table, "schema": schema})
    except Exception as e:
        return _fmt({"error": str(e)})


def _server_get_schema(table: str) -> str:
    conn = _get_server_conn()
    try:
        result = conn(f"meta {table}")
        return _fmt({"table": table, "schema": result.pd().to_dict(orient="records")})
    except Exception as e:
        return _fmt({"error": str(e)})


def _poc_query(sql: str, limit: int = 100) -> str:
    conn = _get_poc_conn()
    try:
        # Append LIMIT if not already present
        if "limit" not in sql.lower():
            sql = sql.rstrip(";") + f" LIMIT {limit}"
        rows = conn.execute(sql).fetchall()
        cols = [d[0] for d in conn.execute(sql).description]
        records = [dict(zip(cols, r)) for r in rows]
        return _fmt({"row_count": len(records), "rows": records})
    except Exception as e:
        return _fmt({"error": str(e), "sql": sql})


def _server_query(q_code: str, limit: int = 100) -> str:
    conn = _get_server_conn()
    try:
        result = conn(q_code)
        if hasattr(result, "pd"):
            df = result.pd().head(limit)
            return _fmt({"row_count": len(df), "rows": df.to_dict(orient="records")})
        return _fmt({"result": str(result)})
    except Exception as e:
        return _fmt({"error": str(e), "q_code": q_code})


def _poc_rfq_analytics(
    desk: str = "",
    date_from: str = "",
    date_to: str = "",
    group_by: str = "trader_id",
    top_n: int = 20,
) -> str:
    conn = _get_poc_conn()
    try:
        conditions = ["1=1"]
        if desk:
            conditions.append(f"desk = '{desk}'")
        if date_from:
            conditions.append(f"rfq_date >= '{date_from}'")
        if date_to:
            conditions.append(f"rfq_date <= '{date_to}'")
        where = " AND ".join(conditions)

        valid_groups = {"trader_id", "desk", "sector", "venue", "trader_name"}
        grp = group_by if group_by in valid_groups else "trader_id"

        # Always include trader_name if grouping by trader_id
        extra_col = ", trader_name" if grp == "trader_id" else ""

        sql = f"""
            SELECT
                {grp}{extra_col},
                COUNT(*)                    AS rfq_count,
                ROUND(AVG(spread_bps), 2)   AS avg_spread_bps,
                SUM(notional_usd)           AS total_notional_usd,
                ROUND(AVG(hit_rate), 4)     AS avg_hit_rate,
                SUM(CASE WHEN won THEN 1 ELSE 0 END) AS wins,
                ROUND(AVG(response_time_ms), 0)      AS avg_response_ms
            FROM bond_rfq
            WHERE {where}
            GROUP BY {grp}{extra_col}
            ORDER BY avg_hit_rate DESC
            LIMIT {top_n}
        """
        rows = conn.execute(sql).fetchall()
        cols = [d[0] for d in conn.execute(sql).description]
        records = [dict(zip(cols, r)) for r in rows]
        meta = {
            "filters": {"desk": desk or "all", "date_from": date_from or "any", "date_to": date_to or "any"},
            "group_by": grp,
            "row_count": len(records),
        }
        return _fmt({"meta": meta, "results": records})
    except Exception as e:
        return _fmt({"error": str(e)})


def _server_rfq_analytics(
    desk: str = "",
    date_from: str = "",
    date_to: str = "",
    group_by: str = "trader_id",
    top_n: int = 20,
) -> str:
    conn = _get_server_conn()
    try:
        desk_filter = f"desk=`{desk}," if desk else ""
        date_filter = ""
        if date_from and date_to:
            date_filter = f"rfq_date within ({date_from.replace('-', '.')}; {date_to.replace('-', '.')})"
            date_filter = date_filter + ","
        elif date_from:
            date_filter = f"rfq_date >= {date_from.replace('-', '.')},"

        grp_sym = f"`{group_by}" if not group_by.startswith("`") else group_by
        q = (
            f"{top_n} sublist `avg_hit_rate xdesc "
            f"select rfq_count:count i, avg_spread_bps:avg spread_bps, "
            f"total_notional_usd:sum notional_usd, avg_hit_rate:avg hit_rate, "
            f"wins:sum won, avg_response_ms:avg response_time_ms "
            f"by {group_by} from bond_rfq where {desk_filter}{date_filter}1b"
        )
        result = conn(q)
        if hasattr(result, "pd"):
            df = result.pd()
            return _fmt({"row_count": len(df), "results": df.to_dict(orient="records")})
        return _fmt({"result": str(result)})
    except Exception as e:
        return _fmt({"error": str(e)})


# ── MCP Server ─────────────────────────────────────────────────────────────────

server = Server("kdb-mcp-server")

_QUERY_LANG = "SQL (DuckDB)" if KDB_MODE == "poc" else "Q (KDB+)"


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="kdb_list_tables",
            description=(
                "List all tables available in the KDB historical data store. "
                f"Running in {KDB_MODE.upper()} mode."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="kdb_get_schema",
            description="Get the schema (column names and types) of a KDB table.",
            inputSchema={
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "Table name (e.g. 'bond_rfq')"},
                },
                "required": ["table"],
            },
        ),
        types.Tool(
            name="kdb_query",
            description=(
                f"Execute a {_QUERY_LANG} query against the KDB historical store. "
                "Returns up to `limit` rows. "
                "Available tables: bond_rfq (desk, trader_id, spread_bps, notional_usd, hit_rate, won, rfq_date, venue, etc.)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": f"{_QUERY_LANG} query to execute",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max rows to return (default: 100)",
                        "default": 100,
                    },
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="kdb_rfq_analytics",
            description=(
                "Run aggregated analytics on Bond RFQ historical data. "
                "Groups by trader/desk/sector/venue and computes: rfq_count, avg_spread_bps, "
                "total_notional_usd, avg_hit_rate, wins. "
                "Use this to answer 'best trader in HY desk last 6 months' type queries. "
                "Spread is in basis points over the UST curve. "
                "Hit rate = fraction of RFQs won (higher = better strategy). "
                "Desks: HY (high yield), IG (investment grade), EM (emerging markets), RATES."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "desk": {
                        "type": "string",
                        "description": "Filter by desk: HY, IG, EM, RATES. Leave empty for all.",
                        "default": "",
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Start date ISO format YYYY-MM-DD. Leave empty for no limit.",
                        "default": "",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "End date ISO format YYYY-MM-DD. Leave empty for no limit.",
                        "default": "",
                    },
                    "group_by": {
                        "type": "string",
                        "description": "Group results by: trader_id (default), desk, sector, venue",
                        "default": "trader_id",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Return top N results ranked by avg_hit_rate (default: 20)",
                        "default": 20,
                    },
                },
                "required": [],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _dispatch, name, arguments)
    except Exception as e:
        result = _fmt({"error": str(e), "tool": name})
    return [types.TextContent(type="text", text=result)]


def _dispatch(name: str, args: dict) -> str:
    if KDB_MODE == "poc":
        if name == "kdb_list_tables":
            return _poc_list_tables()
        if name == "kdb_get_schema":
            return _poc_get_schema(args["table"])
        if name == "kdb_query":
            return _poc_query(args["code"], int(args.get("limit", 100)))
        if name == "kdb_rfq_analytics":
            return _poc_rfq_analytics(
                desk=args.get("desk", ""),
                date_from=args.get("date_from", ""),
                date_to=args.get("date_to", ""),
                group_by=args.get("group_by", "trader_id"),
                top_n=int(args.get("top_n", 20)),
            )
    else:
        if name == "kdb_list_tables":
            return _server_list_tables()
        if name == "kdb_get_schema":
            return _server_get_schema(args["table"])
        if name == "kdb_query":
            return _server_query(args["code"], int(args.get("limit", 100)))
        if name == "kdb_rfq_analytics":
            return _server_rfq_analytics(
                desk=args.get("desk", ""),
                date_from=args.get("date_from", ""),
                date_to=args.get("date_to", ""),
                group_by=args.get("group_by", "trader_id"),
                top_n=int(args.get("top_n", 20)),
            )
    return _fmt({"error": f"Unknown tool: {name}"})


# ── Entry point ────────────────────────────────────────────────────────────────

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    asyncio.run(main())
