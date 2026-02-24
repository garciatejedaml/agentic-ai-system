"""
Strands Multi-Agent Orchestrator

Entry point called by LangGraph. Routes queries to the appropriate pipeline:

  Financial queries (trading, AMPS, KDB, bonds, RFQ, desk, spread)
    → Financial Orchestrator (KDB Agent + AMPS Agent + RAG)

  General queries (everything else)
    → General pipeline (Researcher + Synthesizer)

Routing is keyword-based for low latency — no extra LLM call needed.
"""
from dataclasses import dataclass

from src.agents.researcher import create_researcher
from src.agents.synthesizer import create_synthesizer
from src.config import config
from src.mcp_clients import open_mcp_tools

# Keywords that signal the query should go to the Financial Orchestrator
_FINANCIAL_KEYWORDS = {
    # Trading instruments
    "bond", "rfq", "trader", "trading", "desk", "hy", "ig", "em", "rates",
    "spread", "bps", "basis point", "hit rate", "notional", "yield", "coupon",
    "isin", "cusip", "position", "order",
    # Live / real-time data
    "live", "real-time", "realtime", "current price", "market data", "market-data",
    "bid", "ask", "mid price", "quote", "pnl", "mark to market", "mtm",
    "intraday", "today", "right now", "current position",
    # AMPS specific
    "amps", "sow", "subscribe", "pub/sub", "topic", "publish", "state of world",
    # Data sources
    "kdb", "historical", "history", "6 month", "last month", "last quarter",
    # People/desks
    "best trader", "top trader", "strategy", "performance",
}


def _is_financial_query(query: str) -> bool:
    """Return True if the query should be routed to the Financial Orchestrator."""
    q_lower = query.lower()
    return any(kw in q_lower for kw in _FINANCIAL_KEYWORDS)


@dataclass
class OrchestratorResult:
    research: str
    synthesis: str
    route: str = "general"   # "general" | "financial"


def run_strands_orchestrator(query: str, rag_context: list[dict]) -> OrchestratorResult:
    """
    Entry point called from the LangGraph node.

    Args:
        query:       The original user question.
        rag_context: Pre-retrieved docs from the LangGraph RAG node.

    Returns:
        OrchestratorResult with research, synthesis, and route used.
    """
    # ── Route decision ────────────────────────────────────────────────────────
    if _is_financial_query(query):
        return _run_financial(query, rag_context)
    return _run_general(query, rag_context)


# ── Financial pipeline ────────────────────────────────────────────────────────

def _run_financial(query: str, rag_context: list[dict]) -> OrchestratorResult:
    """Route to the Financial Orchestrator (KDB + AMPS + RAG).

    Phase 2: calls the Financial Orchestrator via A2A HTTP if
    FINANCIAL_ORCHESTRATOR_URL is set to a remote service.
    Falls back to in-process call (Phase 1 behavior) when running
    the monolith (AGENT_SERVICE not set or AGENT_SERVICE=api).
    """
    import os
    from src.agents.synthesizer import create_synthesizer

    rag_text = ""
    if rag_context:
        rag_text = "\n\n".join(f"[{i+1}] {doc['text']}" for i, doc in enumerate(rag_context))

    print(f"[Orchestrator] Route → Financial (KDB + AMPS + RAG)")

    # Phase 2: delegate to Financial Orchestrator service via A2A HTTP
    agent_service = os.getenv("AGENT_SERVICE", "")
    fin_url = os.getenv("FINANCIAL_ORCHESTRATOR_URL", "")
    if agent_service == "api" and fin_url:
        from src.a2a.client import call_agent_sync
        from src.a2a.registry import get_endpoint
        endpoint = get_endpoint("financial-orchestrator", fin_url)
        full_query = query
        if rag_text:
            full_query = f"{query}\n\n[Pre-retrieved knowledge base context]\n{rag_text}"
        research_text = call_agent_sync(endpoint, full_query)
    else:
        # Phase 1 fallback: in-process call
        from src.agents.financial_orchestrator import run_financial_orchestrator
        research_text = run_financial_orchestrator(query, rag_context=rag_text)

    synthesizer = create_synthesizer()
    synthesis_prompt = (
        f"Original question: {query}\n\n"
        f"Financial analysis findings:\n{research_text}\n\n"
        "Please synthesize a clear, structured answer focused on actionable insights."
    )
    synthesis_text = str(synthesizer(synthesis_prompt))

    return OrchestratorResult(research=research_text, synthesis=synthesis_text, route="financial")


# ── General pipeline ──────────────────────────────────────────────────────────

def _run_general(query: str, rag_context: list[dict]) -> OrchestratorResult:
    """Original general-purpose pipeline: Researcher + Synthesizer."""
    pre_context_block = ""
    if rag_context:
        snippets = "\n\n".join(
            f"[{i+1}] {doc['text']}" for i, doc in enumerate(rag_context)
        )
        pre_context_block = (
            f"\n\nPre-retrieved context from RAG (use as starting point):\n{snippets}"
        )

    research_prompt = (
        f"Research the following question thoroughly: {query}{pre_context_block}"
    )

    print(f"[Orchestrator] Route → General (Researcher + Synthesizer)")
    with open_mcp_tools(docs_path=config.MCP_FILESYSTEM_PATH) as mcp_tools:
        researcher = create_researcher(extra_tools=mcp_tools)
        research_response = researcher(research_prompt)

    research_text = str(research_response)

    synthesizer = create_synthesizer()
    synthesis_prompt = (
        f"Original question: {query}\n\n"
        f"Research findings:\n{research_text}\n\n"
        "Please synthesize a clear, structured answer."
    )
    synthesis_text = str(synthesizer(synthesis_prompt))

    return OrchestratorResult(research=research_text, synthesis=synthesis_text, route="general")
