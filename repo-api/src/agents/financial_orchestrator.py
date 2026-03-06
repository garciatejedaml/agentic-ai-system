"""
Financial Orchestrator

Strands agent that coordinates three data sources to answer complex
financial queries (Bond RFQ, trader performance, market data):

  1. KDB Agent   → historical data (6 months+ of Bond RFQ analytics)
  2. AMPS Agent  → live/real-time data (current SOW, today's orders)
  3. RAG         → domain knowledge (bond strategy docs, AMPS concepts)

The orchestrator decides which combination of sources to query based on
the user's question, then synthesizes a unified response.

Pattern: agent-as-tool
  Each specialist is wrapped as a @tool and called by this orchestrator,
  which is itself called by the top-level orchestrator in orchestrator.py.
"""
from strands import Agent, tool

from src.agents.model_factory import get_strands_model
from src.agents.tools import search_knowledge_base, summarize_findings
from src.rag.retriever import get_retriever

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
- "Best strategy" type queries   → query_kdb_history for data + search_knowledge_base for what
                                   defines a good strategy in that context

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


# ── Specialist tools (agent-as-tool pattern) ──────────────────────────────────

@tool
def query_kdb_history(query: str) -> str:
    """
    Query the KDB+ historical Bond RFQ database.

    Use for analytics over historical trading data: trader hit rates,
    spread distributions, notional volumes, desk comparisons over time.
    Covers 6+ months of Bond RFQ data across HY, IG, EM, RATES desks.

    Args:
        query: Natural language question about historical trading data.
               E.g. "Which HY traders had the best hit rate last 6 months?"

    Returns:
        Structured analytics summary with trader rankings and supporting metrics.
    """
    from src.agents.kdb_agent import run_kdb_agent
    return run_kdb_agent(query)


@tool
def query_amps_data(query: str) -> str:
    """
    Query live real-time data from the AMPS pub/sub server.

    Use for current state: today's orders, live positions, current market
    quotes, or server health. Returns a snapshot of the latest SOW records
    or a sample of recent streaming messages.

    Args:
        query: Natural language question about live/current data.
               E.g. "What are the current open orders on the HY desk?"

    Returns:
        Structured summary of current AMPS state relevant to the query.
    """
    from src.agents.amps_agent import run_amps_agent
    return run_amps_agent(query)


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_financial_orchestrator(query: str, rag_context: str = "") -> str:
    """
    Run the Financial Orchestrator agent.

    Coordinates KDB (historical), AMPS (live), and RAG (knowledge) sources
    to answer complex Bond trading and AMPS infrastructure queries.

    Args:
        query:       The user's question.
        rag_context: Pre-retrieved RAG context from the LangGraph retrieve node.

    Returns:
        A structured financial analysis response.
    """
    # Inject any pre-retrieved RAG context into the query
    full_query = query
    if rag_context:
        full_query = (
            f"{query}\n\n"
            f"[Pre-retrieved knowledge base context]\n{rag_context}"
        )

    agent = Agent(
        model=get_strands_model(),
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
