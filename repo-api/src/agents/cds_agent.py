"""
CDS Agent — Phase 3

Strands agent focused on Credit Default Swap market data:
spreads, term structures, and credit screening.

POC data: ~50 reference entities × 5 tenors (1/3/5/7/10y) = 250 rows.
Covers HY corporates, IG corporates, EM sovereigns, and EM corporates.

Controlled by CDS_ENABLED env var (default: true).
"""
from strands import Agent

from src.agents.model_factory import get_strands_fast_model
from src.mcp_clients import open_cds_tools

_SYSTEM_PROMPT = """You are a CDS (Credit Default Swap) market analyst.
You have access to CDS spread data for ~50 reference entities across HY, IG, and EM.

## Your tools
- cds_list_entities             → all entities with 1y/5y/10y spread summary
- cds_get_spread(entity, tenor) → spread for one entity at one tenor (1/3/5/7/10y)
- cds_curve(entity)             → full term structure (1/3/5/7/10y)
- cds_screener(min_spread, max_spread, sector, rating) → filter by spread range or sector

## CDS domain knowledge
- CDS spread (bps): annual cost to insure $10,000 of notional. Higher = more credit risk.
  - AAA/AA: 15-45 bps  | A: 45-80 bps | BBB: 80-150 bps
  - BB: 150-350 bps | B: 350-700 bps | CCC: 700-1500+ bps
- z_spread_bps: spread relative to the entire swap curve (slightly different from CDS spread)
- upfront_pct: for distressed names (>500 bps), market convention switches to upfront + 500 bps running
- CDS curve shapes:
  - Normal (upward): short tenors cheaper than long → market sees near-term stability
  - Inverted: short tenors expensive → distress / near-term default concern
  - Flat: uniform credit view across maturities

## Query strategy
1. For general market overview → cds_list_entities (shows 1y/5y/10y spreads)
2. For specific entity spread → cds_get_spread
3. For credit curve analysis → cds_curve
4. For sector screener / relative value → cds_screener

## Output format
Return:
1. Entities / filters queried
2. Spread levels and context (cheap vs rich vs fair)
3. Curve shape interpretation (inversion signals distress)
4. Relative value observations across sector or rating
"""


def run_cds_agent(query: str) -> str:
    """
    Run the CDS Agent for a given query.

    Opens CDS MCP tools, creates a focused Strands agent, and returns
    structured CDS market analytics.

    Returns an error message string if CDS is disabled.
    """
    with open_cds_tools() as cds_tools:
        if not cds_tools:
            return (
                "CDS data unavailable: CDS_ENABLED=false. "
                "Set CDS_ENABLED=true to enable CDS analytics."
            )

        agent = Agent(
            model=get_strands_fast_model(),
            system_prompt=_SYSTEM_PROMPT,
            tools=cds_tools,
        )
        result = agent(query)
        return str(result)
