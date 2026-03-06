"""
Financial Orchestrator v2 (Phase 2 — A2A)

Same logic as financial_orchestrator.py but the @tool functions
call KDB Agent and AMPS Agent via HTTP (A2A protocol) instead of
importing and calling them directly in-process.

The Financial Orchestrator discovers agent endpoints:
  1. First tries DynamoDB registry (runtime discovery)
  2. Falls back to config env vars (KDB_AGENT_URL, AMPS_AGENT_URL)

This means:
  - KDB Agent can be scaled independently (10 replicas)
  - AMPS Agent can be on a different host/region
  - Agents can be swapped at runtime without redeploying the orchestrator

Pattern: agent-as-tool (same as v1), but tools make HTTP calls.
"""
from strands import Agent, tool

from src.a2a.client import call_agent_sync
from src.a2a.registry import get_endpoint
from src.agents.model_factory import get_strands_fast_model
from src.agents.tools import search_knowledge_base, summarize_findings

_SYSTEM_PROMPT = """You are a Senior Bond Trading Analyst with access to three data sources:

1. **KDB historical data** (query_kdb_history tool)
   - 6+ months of Bond RFQ records across HY, IG, EM, RATES desks
   - Use for: trader rankings, historical hit rates, notional trends, spread analysis
   - When to use: questions about "last X months", "best trader", "historical performance"

2. **AMPS live data** (query_amps_data tool)
   - Real-time current state: today's orders, live positions, market quotes
   - Use for: "current positions", "live orders", "what's happening now"
   - When to use: queries about current state, intraday, "right now"

3. **Knowledge base** (search_knowledge_base tool)
   - AMPS documentation, bond market concepts, strategy definitions
   - Use for: understanding what metrics mean, AMPS configuration, strategy context
   - When to use: "what does X mean", "how does AMPS work", conceptual questions

## Decision logic
- Historical performance query   → query_kdb_history (primary) + search_knowledge_base (context)
- Current state / live query     → query_amps_data (primary)
- Both historical + live needed  → call both, merge results
- Conceptual / doc question      → search_knowledge_base only
- "Best strategy" type queries   → query_kdb_history for data + search_knowledge_base for context

## CRITICAL: Be proactive — query first, never ask for clarification
When the query is ambiguous on time period or metrics, USE SENSIBLE DEFAULTS immediately:
- Time period not specified → use last 6 months (date_from = 6 months ago from today)
- Desk not specified → HY if context suggests bonds/credit, else query all desks
- Metric not specified → rank by avg_hit_rate (standard measure of strategy quality)
- NEVER ask the user to clarify before calling a tool.
- ALWAYS call query_kdb_history or query_amps_data first, then enrich with search_knowledge_base.
- Show the data and numbers first, then explain what they mean.
- If you need more detail after the first tool call, call another tool — do not ask the user.

## Response structure
Always produce:
1. **Data sources used** (which tools were called)
2. **Key findings** — ranked results with specific numbers
3. **Analysis** — what the data means in trading context
4. **Confidence level** — HIGH / MEDIUM / LOW with brief justification

## Bond domain knowledge
- Desks: HY (high yield, BB and below), IG (investment grade, BBB+ and above),
         EM (emerging markets), RATES (government bonds)
- HY desk: higher spreads (200–600 bps), higher risk, wider bid/ask
- hit_rate: fraction of RFQs won — measures pricing competitiveness
- spread_bps: basis points over UST benchmark curve
- A good HY trader: high hit_rate WITHOUT sacrificing spread discipline
  (winning by being the cheapest is not a sustainable strategy)
"""


# ── A2A-backed specialist tools ───────────────────────────────────────────────

@tool
def query_kdb_history(query: str) -> str:
    """
    Query the KDB+ historical Bond RFQ database via A2A HTTP.

    Routes to the KDB Agent service (isolated container). Use for analytics
    over historical trading data: trader hit rates, spread distributions,
    notional volumes, desk comparisons over time.
    Covers 6+ months of Bond RFQ data across HY, IG, EM, RATES desks.

    Args:
        query: Natural language question about historical trading data.

    Returns:
        Structured analytics summary from the KDB Agent service.
    """
    from src.config import config
    endpoint = get_endpoint("kdb-agent", config.KDB_AGENT_URL)
    return call_agent_sync(endpoint, query, timeout=config.A2A_TIMEOUT)


@tool
def query_amps_data(query: str) -> str:
    """
    Query live real-time data from the AMPS pub/sub server via A2A HTTP.

    Routes to the AMPS Agent service (isolated container). Use for current
    state: today's orders, live positions, current market quotes, or server
    health. Returns a snapshot of the latest SOW records.

    Args:
        query: Natural language question about live/current data.

    Returns:
        Structured summary of current AMPS state from the AMPS Agent service.
    """
    from src.config import config
    endpoint = get_endpoint("amps-agent", config.AMPS_AGENT_URL)
    return call_agent_sync(endpoint, query, timeout=config.A2A_TIMEOUT)


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_financial_orchestrator_v2(query: str, rag_context: str = "") -> str:
    """
    Run the Financial Orchestrator v2 (A2A version).

    Coordinates KDB (historical), AMPS (live), and RAG (knowledge) sources
    via HTTP A2A calls to independent agent services.

    Args:
        query:       The user's question.
        rag_context: Pre-retrieved RAG context from the LangGraph retrieve node.

    Returns:
        A structured financial analysis response.
    """
    full_query = query
    if rag_context:
        full_query = (
            f"{query}\n\n"
            f"[Pre-retrieved knowledge base context]\n{rag_context}"
        )

    agent = Agent(
        model=get_strands_fast_model(),
        system_prompt=_SYSTEM_PROMPT,
        tools=[
            query_kdb_history,
            query_amps_data,
            search_knowledge_base,
            summarize_findings,
        ],
    )

    result = agent(full_query)
    return str(result)
