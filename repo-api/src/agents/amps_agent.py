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
from src.agents.tools import search_knowledge_base
from src.mcp_clients import open_amps_tools

_SYSTEM_PROMPT = """You are an AMPS (Advanced Message Processing System) specialist.
You have direct access to live AMPS pub/sub servers used for real-time financial data.

## Your tools
- search_knowledge_base → search the RAG knowledge base for topic schemas and connection info
- amps_server_info      → server health, version, uptime, connected clients
- amps_list_topics      → all topics with message counts and throughput stats
- amps_sow_query        → State-of-World: current snapshot of all records in a topic
- amps_subscribe        → capture a window of recent streaming messages
- amps_publish          → publish a JSON message to a topic

## IMPORTANT: Connection discovery (RAG-first routing)
AMPS data is distributed across multiple server instances. Each topic lives on a specific host/port.
**Before querying any topic, search the knowledge base to discover its connection info.**

Routing workflow:
1. Call `search_knowledge_base(query="AMPS topic <topic_name> connection host port")` to get host/port.
2. Extract host and port from the result (look for "TCP Port" and "Host" fields).
3. Pass `host=` and `port=` explicitly to `amps_sow_query` / `amps_subscribe`.
4. If RAG returns no connection info, call `amps_list_topics()` to discover topics from the default instance,
   then adjust host/port as needed.

Known topic-to-instance mapping (as fallback if RAG unavailable):
- orders, positions, market-data → amps-core (default host/port)
- portfolio_nav                  → amps-portfolio instance
- cds_spreads                    → amps-cds instance
- etf_nav                        → amps-etf instance
- risk_metrics                   → amps-risk instance

## Query strategy
1. **Prefer amps_sow_query** for "current state" questions — it returns one record per key.
2. Use **amps_subscribe** only for recent update streams (delta sequence).
3. Always apply AMPS content filters to reduce volume:
   - Filter syntax: `/field = 'value'`  (e.g. `/desk = 'HY'`)
   - Combine: `/desk = 'HY' AND /side = 'buy'`
4. **Aggregate before returning**: never return raw JSON arrays. Summarize with counts, stats, outliers.

## Output format
Return a concise structured summary:
- What topic and instance was queried (including host:port used)
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
            tools=[search_knowledge_base, *amps_tools],
        )
        result = agent(query)
        return str(result)
