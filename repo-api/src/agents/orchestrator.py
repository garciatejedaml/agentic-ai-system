"""
Strands Multi-Agent Orchestrator

Entry point called by LangGraph. Routes queries to the appropriate pipeline:

  Financial queries (trading, AMPS, KDB, bonds, RFQ, desk, spread)
    → Phase 3: LLM Router → parallel specialist agents
    → Phase 2 fallback: Financial Orchestrator (KDB Agent + AMPS Agent + RAG)

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
    """Route to the financial pipeline.

    Phase 3 (default): LLM Router reads DynamoDB, picks specialist agents,
    calls them in parallel or sequentially via A2A HTTP.

    Phase 2 fallback: delegates to financial-orchestrator service.
    Phase 1 fallback: in-process call.
    """
    import os
    from src.agents.synthesizer import create_synthesizer

    rag_text = ""
    if rag_context:
        rag_text = "\n\n".join(f"[{i+1}] {doc['text']}" for i, doc in enumerate(rag_context))

    full_query = query
    if rag_text:
        full_query = f"{query}\n\n[Pre-retrieved knowledge base context]\n{rag_text}"

    print(f"[Orchestrator] Route → Financial (Phase 3 LLM Router)")

    agent_service = os.getenv("AGENT_SERVICE", "")

    # ── Phase 3: LLM Router + parallel/sequential specialist agents ───────────
    if agent_service == "api":
        from src.agents.llm_router import route_query
        from src.a2a.parallel_client import call_agents_parallel_sync

        decision = route_query(query)

        if decision.strategy == "sequential":
            # Sequential: call agents one by one (risk-pnl handles internal sequencing)
            results: dict[str, str] = {}
            for agent_id in decision.agents:
                results.update(call_agents_parallel_sync([agent_id], full_query))
        else:
            # Parallel: all agents called concurrently
            results = call_agents_parallel_sync(decision.agents, full_query)

        if len(results) == 1:
            research_text = list(results.values())[0]
        else:
            research_text = _merge_parallel_results(query, results)

        return OrchestratorResult(research=research_text, synthesis=research_text, route="financial")

    # ── Phase 2 fallback: financial-orchestrator via A2A ──────────────────────
    fin_url = os.getenv("FINANCIAL_ORCHESTRATOR_URL", "")
    if fin_url:
        from src.a2a.client import call_agent_sync
        from src.a2a.registry import get_endpoint
        endpoint = get_endpoint("financial-orchestrator", fin_url)
        research_text = call_agent_sync(endpoint, full_query)
        return OrchestratorResult(research=research_text, synthesis=research_text, route="financial")

    # ── Phase 1 fallback: in-process ──────────────────────────────────────────
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


def _merge_parallel_results(query: str, results: dict[str, str]) -> str:
    """Merge N agent results into one structured response with per-agent sections."""
    sections = []
    for agent_id, result in results.items():
        header = agent_id.replace("-", " ").title()
        sections.append(f"## {header}\n\n{result}")
    merged = "\n\n---\n\n".join(sections)
    return f"# Multi-Source Financial Analysis\n\nQuery: {query}\n\n{merged}"


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
