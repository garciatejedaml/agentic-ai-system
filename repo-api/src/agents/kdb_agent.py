"""
KDB Historical Data Agent

Strands agent focused exclusively on historical Bond RFQ analytics stored
in KDB+. Only opens KDB MCP tools.

Responsibilities:
  - Trader performance analytics over historical periods
  - Desk-level aggregations (HY, IG, EM, RATES)
  - Hit rate, spread, notional and win/loss analysis
  - Custom SQL (poc mode) or Q (server mode) queries

Used as a sub-agent called by the Financial Orchestrator.

Backend modes (transparent to this agent):
  KDB_MODE=poc    → DuckDB reads Parquet files  (no license needed)
  KDB_MODE=server → PyKX connects to real KDB+ server
"""
import os

from strands import Agent

from src.agents.model_factory import get_strands_fast_model
from src.mcp_clients import open_kdb_tools

_KDB_MODE = os.getenv("KDB_MODE", "poc")

_SYSTEM_PROMPT_POC = """You are a KDB historical data analyst specializing in Bond RFQ analytics.
You query a DuckDB database (KDB POC mode) containing historical Bond RFQ data using SQL.

## Your tools
- kdb_list_tables          → list available tables
- kdb_get_schema(table)    → column names and types
- kdb_query(code)          → execute SQL query (returns up to `limit` rows)
- kdb_rfq_analytics(...)   → high-level aggregated RFQ analytics (use this first)

## Main table: bond_rfq
Columns:
  rfq_id, desk, trader_id, trader_name, isin, bond_name, issuer, sector,
  rating, side, notional_usd, price, spread_bps, coupon,
  rfq_date (DATE), rfq_time, response_time_ms, won (BOOLEAN), hit_rate, venue

Desks: HY (high yield), IG (investment grade), EM (emerging markets), RATES
Venues: Bloomberg, TradeWeb, MarketAxess, Voice, D2C

## Domain knowledge
- spread_bps: basis points over the UST (US Treasury) benchmark curve
  Lower spread = tighter pricing = better for the client (harder to win)
- hit_rate: fraction of RFQs won by a trader (higher = better strategy)
- notional_usd: face value of the bond position in USD
- A "best strategy" trader: high hit_rate AND reasonable spread (not just cheapest)

## Query strategy
1. **Always start with kdb_rfq_analytics** for trader/desk aggregations.
   It already computes avg_spread_bps, avg_hit_rate, total_notional, wins.
2. Use **kdb_query with SQL** for custom analysis not covered by kdb_rfq_analytics.
3. Apply date filters when the user mentions a time period.
4. GROUP BY trader_id for per-trader analysis; GROUP BY desk for desk comparisons.

## Output format
Return a structured analysis:
- Period covered and filters applied
- Top performers ranked by hit_rate with supporting metrics
- Notable patterns (e.g. trader with best spread discipline, fastest response)
- Confidence: HIGH for direct aggregations, MEDIUM for sampled data
"""

_SYSTEM_PROMPT_SERVER = """You are a KDB+ Q language analyst specializing in Bond RFQ analytics.
You query a live KDB+ server containing historical Bond RFQ data using Q code.

## Your tools
- kdb_list_tables          → list available tables
- kdb_get_schema(table)    → column names and types (meta table)
- kdb_query(code)          → execute Q code
- kdb_rfq_analytics(...)   → high-level aggregated RFQ analytics (use this first)

## Main table: bond_rfq
Columns: rfq_id, desk, trader_id, trader_name, isin, bond_name, issuer, sector,
         rating, side, notional_usd, price, spread_bps, coupon,
         rfq_date (date), rfq_time (time), response_time_ms (long), won (boolean),
         hit_rate (float), venue

Desks: `HY `IG `EM `RATES  (KDB+ symbols use backtick prefix)

## Q syntax examples
```q
/ Best HY traders last 6 months
select rfq_count:count i, avg_spread:avg spread_bps, avg_hit:avg hit_rate, total_notional:sum notional_usd
  by trader_id, trader_name
  from bond_rfq
  where desk=`HY, rfq_date within (2024.08.01; 2025.02.22)

/ Desk comparison
select rfq_count:count i, avg_hit:avg hit_rate by desk from bond_rfq
```

## Domain knowledge
- spread_bps: basis points over UST curve
- hit_rate: fraction of RFQs won (higher = better)
- Symbols in Q need backtick: `HY not 'HY'

## Output format
Return structured analysis with top performers, supporting metrics, patterns.
Confidence: HIGH for direct KDB queries.
"""

_SYSTEM_PROMPT = _SYSTEM_PROMPT_SERVER if _KDB_MODE == "server" else _SYSTEM_PROMPT_POC


def run_kdb_agent(query: str) -> str:
    """
    Run the KDB Historical Data Agent for a given query.

    Opens KDB MCP tools, creates a focused Strands agent, and returns
    structured analytics from historical Bond RFQ data.

    Returns an error message string if KDB is disabled or unavailable.
    """
    with open_kdb_tools() as kdb_tools:
        if not kdb_tools:
            return (
                "KDB historical data unavailable: KDB_ENABLED=false. "
                "Set KDB_ENABLED=true and run: python scripts/generate_synthetic_rfq.py"
            )

        agent = Agent(
            model=get_strands_fast_model(),
            system_prompt=_SYSTEM_PROMPT,
            tools=kdb_tools,
        )
        result = agent(query)
        return str(result)
