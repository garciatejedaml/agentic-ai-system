"""
Portfolio Agent — Phase 3

Strands agent focused on portfolio holdings, exposure, and concentration analytics.
Uses the Portfolio MCP server (in-memory POC data with 5 portfolios).

Portfolios: HY_MAIN, IG_CORE, EM_BLEND, RATES_GOV, MULTI_STRAT
Each with 15 bond positions (~75 total rows).

Controlled by PORTFOLIO_ENABLED env var (default: true).
"""
import os

from strands import Agent

from src.agents.model_factory import get_strands_fast_model
from src.mcp_clients import open_portfolio_tools

_SYSTEM_PROMPT = """You are a Portfolio Analytics specialist.
You have access to live portfolio positions across 5 fixed income portfolios:
  HY_MAIN (High Yield), IG_CORE (Investment Grade), EM_BLEND (Emerging Markets),
  RATES_GOV (Government), MULTI_STRAT (Multi-Strategy).

## Your tools
- portfolio_list                    → all portfolios with market value, duration, spread summary
- portfolio_holdings(portfolio_id)  → full position list (ISIN, issuer, weight, duration, spread)
- portfolio_exposure(desk, asset_class) → sector-level aggregation with weights
- portfolio_concentration(portfolio_id, top_n) → top N positions by market value

## Query strategy
1. For general portfolio questions → start with portfolio_list
2. For specific portfolio details → portfolio_holdings
3. For sector exposure / risk concentration → portfolio_exposure
4. For concentration / single-name risk → portfolio_concentration

## Domain knowledge
- weight_pct: % of portfolio NAV in that position
- duration_years: price sensitivity to interest rate moves (higher = more rate risk)
- spread_bps: credit spread over UST benchmark (higher = more credit risk)
- HY desk: spread 200-600 bps (higher credit risk), duration 2-6y
- IG desk: spread 50-180 bps (lower credit risk), duration 3-10y
- EM desk: sovereign + corporate risk, spread 150-450 bps
- RATES desk: UST/agency only, spread 5-60 bps, long duration (1-20y)

## Output format
Return structured data with:
1. Portfolio(s) queried and filters applied
2. Key metrics (total NAV, weighted avg duration, weighted avg spread)
3. Top holdings or sector breakdown as relevant
4. Risk observations (concentration, duration/credit risk)
"""


def run_portfolio_agent(query: str) -> str:
    """
    Run the Portfolio Agent for a given query.

    Opens Portfolio MCP tools, creates a focused Strands agent, and returns
    structured portfolio analytics.

    Returns an error message string if Portfolio is disabled.
    """
    with open_portfolio_tools() as portfolio_tools:
        if not portfolio_tools:
            return (
                "Portfolio data unavailable: PORTFOLIO_ENABLED=false. "
                "Set PORTFOLIO_ENABLED=true to enable portfolio analytics."
            )

        agent = Agent(
            model=get_strands_fast_model(),
            system_prompt=_SYSTEM_PROMPT,
            tools=portfolio_tools,
        )
        result = agent(query)
        return str(result)
