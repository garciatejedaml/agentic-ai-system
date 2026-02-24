"""
AMPS Specialist Agent

Strands agent focused exclusively on live/real-time data from the AMPS
pub/sub server. Only opens AMPS MCP tools — no KDB, no web search.

Responsibilities:
  - Current state queries via SOW (State of World)
  - Live topic subscriptions for recent message samples
  - Server health and topic statistics
  - Publishing test/event messages to topics

Used as a sub-agent called by the Financial Orchestrator.
"""
from strands import Agent

from src.agents.model_factory import get_strands_fast_model
from src.mcp_clients import open_amps_tools

_SYSTEM_PROMPT = """You are an AMPS (Advanced Message Processing System) specialist.
You have direct access to a live AMPS pub/sub server used for real-time financial data.

## Your tools
- amps_server_info    → server health, version, uptime, connected clients
- amps_list_topics    → all topics with message counts and throughput stats
- amps_sow_query      → State-of-World: current snapshot of all records in a topic
- amps_subscribe      → capture a window of recent streaming messages
- amps_publish        → publish a JSON message to a topic

## Available topics
- orders       → live bond orders  (desk, trader_id, isin, notional_usd, side, price, spread_bps)
- positions    → current trader positions  (trader_id, isin, quantity, avg_cost)
- market-data  → live bond prices  (isin, bid, ask, mid, spread_bps, timestamp)

## Query strategy
1. **Prefer amps_sow_query** for "current state" questions — it returns one record per key.
   Much lighter than subscribe for large topics.
2. Use **amps_subscribe** only when you need the sequence of recent updates (delta stream).
3. Always apply AMPS content filters to reduce volume:
   - Filter syntax: `/field = 'value'`  (e.g. `/desk = 'HY'`, `/trader_id = 'T_HY_001'`)
   - Combine: `/desk = 'HY' AND /side = 'buy'`
4. **Aggregate before returning**: never return raw JSON arrays.
   Summarize: count, key stats, notable outliers.

## Output format
Return a concise structured summary:
- What data source was queried and what filters were applied
- Key statistics (counts, averages, ranges)
- Specific records relevant to the question
- Confidence: HIGH if SOW/live data, MEDIUM if sampled via subscribe
"""


def run_amps_agent(query: str) -> str:
    """
    Run the AMPS Specialist Agent for a given query.

    Opens AMPS MCP tools, creates a focused Strands agent, and returns
    a structured summary of live/real-time data relevant to the query.

    Returns an error message string if AMPS is disabled or unavailable.
    """
    with open_amps_tools() as amps_tools:
        if not amps_tools:
            return (
                "AMPS data unavailable: AMPS_ENABLED=false or server not reachable. "
                "Start the AMPS server with: docker compose -f docker-compose.amps.yml up -d"
            )

        agent = Agent(
            model=get_strands_fast_model(),
            system_prompt=_SYSTEM_PROMPT,
            tools=amps_tools,
        )
        result = agent(query)
        return str(result)
