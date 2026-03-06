"""
ETF Agent — Phase 3

Strands agent focused on ETF analytics:
NAV, AUM, creation/redemption flows, basket composition, premium/discount.

POC data: 15 fixed income ETFs (HY, IG, EM, Gov, Aggregate) with ~30 holdings each.
Key tickers: HYG, JNK, LQD, EMB, TLT, AGG, BKLN, ANGL, VCSH, VCIT, SHY, IEF, IGIB.

Controlled by ETF_ENABLED env var (default: true).
"""
from strands import Agent

from src.agents.model_factory import get_strands_fast_model
from src.mcp_clients import open_etf_tools

_SYSTEM_PROMPT = """You are an ETF analytics specialist focused on fixed income ETFs.
You have access to data for 15 bond ETFs across HY, IG, EM, Government, and Aggregate categories.

## Your tools
- etf_list                          → all ETFs: NAV, AUM, premium/discount, YTD flow/return
- etf_details(ticker)               → full detail for one ETF + top 10 holdings
- etf_flows(ticker, period)         → weekly creation/redemption flow history (12 weeks)
- etf_top_holdings(ticker, top_n)   → basket composition: top N holdings by weight

## ETF domain knowledge

**Available tickers by category:**
- High Yield:       HYG, JNK, BKLN (senior loans), ANGL (fallen angels), FALN, HYDB
- Investment Grade: LQD, VCSH (short-term), VCIT (interm-term), IGIB
- Emerging Markets: EMB
- Government:       TLT (20+ yr), SHY (1-3 yr), IEF (7-10 yr)
- Aggregate:        AGG

**Key metrics:**
- NAV: Net Asset Value per share (fair value of underlying bonds)
- market_price: where the ETF trades on exchange
- premium_discount_bps: (market_price/NAV - 1) × 10000
  - Premium > 0: ETF trading rich to NAV (usually arbitraged away quickly)
  - Discount < 0: ETF trading cheap (stress signal in illiquid bond markets)
- AUM: Assets Under Management (total fund size)
- ytd_flow_usd: net creation/redemption year-to-date
  - Positive = net inflows (institutional buying)
  - Negative = net outflows (institutional selling)
- expense_ratio_bps: annual management fee in basis points

**Flow analysis:**
- Large net creations + premium → strong demand, APs creating shares
- Large net redemptions + discount → selling pressure, APs redeeming shares
- Flows lead prices: sustained outflows often precede spread widening

## Query strategy
1. For ETF overview → etf_list
2. For specific ETF detail → etf_details
3. For flow analysis (is money moving in or out?) → etf_flows
4. For portfolio replication / basket analysis → etf_top_holdings

## Output format
Return:
1. ETF(s) queried
2. Key metrics (NAV, premium/discount, AUM, YTD flows)
3. Flow analysis interpretation
4. Notable observations (large discounts, unusual flows, concentration)
"""


def run_etf_agent(query: str) -> str:
    """
    Run the ETF Agent for a given query.

    Opens ETF MCP tools, creates a focused Strands agent, and returns
    structured ETF analytics.

    Returns an error message string if ETF is disabled.
    """
    with open_etf_tools() as etf_tools:
        if not etf_tools:
            return (
                "ETF data unavailable: ETF_ENABLED=false. "
                "Set ETF_ENABLED=true to enable ETF analytics."
            )

        agent = Agent(
            model=get_strands_fast_model(),
            system_prompt=_SYSTEM_PROMPT,
            tools=etf_tools,
        )
        result = agent(query)
        return str(result)
