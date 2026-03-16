"""
LangGraph node functions.

Each function receives the current AgentState and returns a dict with
the fields it wants to update. LangGraph merges the returned dict into state.

Graph topology:
    intake_node → retrieve_node → strands_node → format_node → END
"""
from __future__ import annotations

import time
import traceback

from src.graph.state import AgentState
from src.rag.retriever import get_retriever

# Errors from Anthropic / LiteLLM that indicate transient overload — safe to retry
_RETRYABLE_PHRASES = ("overloaded", "serviceunvailable", "rate_limit", "529", "too many requests")
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 5  # seconds; doubles each attempt (5 → 10 → 20)


# ── Node 1: Intake ────────────────────────────────────────────────────────────

def intake_node(state: AgentState) -> dict:
    """
    Validate and normalise the incoming query.
    First node in the graph — light pre-processing only.
    """
    query = (state.get("query") or "").strip()
    if not query:
        return {"error": "Empty query received.", "final_response": "Please provide a question."}
    return {"query": query, "error": None}


# ── Node 2: RAG Retrieval ─────────────────────────────────────────────────────

def retrieve_node(state: AgentState) -> dict:
    """
    Query the knowledge base and attach the top-k relevant document chunks to state.
    Skipped for financial queries — specialist agents and amps-agent do their own RAG.
    """
    if state.get("error"):
        return {}

    # Financial queries are handled by the LLM Router → specialist agents.
    # Each agent (esp. amps-agent) runs its own search_knowledge_base call.
    # Skip in-process retrieval here to avoid loading SentenceTransformer
    # twice and spiking memory in the api-service worker.
    from src.agents.orchestrator import _is_financial_query
    if _is_financial_query(state.get("query", "")):
        return {"rag_context": []}

    try:
        retriever = get_retriever()
        docs = retriever.retrieve(state["query"])
        return {"rag_context": docs}
    except Exception as exc:
        return {"error": f"RAG retrieval failed: {exc}", "rag_context": []}


# ── Node 3: Strands Multi-Agent ───────────────────────────────────────────────

def strands_node(state: AgentState) -> dict:
    """
    Invoke the Strands multi-agent orchestrator.

    This is the 'agentic' node: internally it runs Researcher + Synthesizer
    agents sequentially. LangGraph treats the whole thing as a single node.
    """
    if state.get("error"):
        return {}

    from src.agents.orchestrator import run_strands_orchestrator

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            result = run_strands_orchestrator(
                query=state["query"],
                rag_context=state.get("rag_context") or [],
            )
            return {
                "research": result.research,
                "synthesis": result.synthesis,
                "routing_plan": result.routing_plan,
                "confidence": result.confidence,
            }
        except Exception as exc:
            exc_str = str(exc).lower()
            is_retryable = any(phrase in exc_str for phrase in _RETRYABLE_PHRASES)
            if is_retryable and attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                print(f"[strands_node] Anthropic overloaded (attempt {attempt}/{_MAX_RETRIES}), retrying in {delay}s...")
                time.sleep(delay)
                last_exc = exc
            else:
                tb = traceback.format_exc()
                return {"error": f"Strands agents failed: {exc}\n{tb}"}

    tb = traceback.format_exc()
    return {"error": f"Strands agents failed after {_MAX_RETRIES} retries: {last_exc}\n{tb}"}


# ── Node 4: Format Response ────────────────────────────────────────────────────

def format_node(state: AgentState) -> dict:
    """
    Assemble the final user-facing response from synthesis (or error).
    """
    if state.get("error"):
        return {"final_response": f"Error: {state['error']}"}

    synthesis = state.get("synthesis", "")
    rag_context = state.get("rag_context") or []

    sources_block = ""
    if rag_context:
        unique_sources = sorted({d["source"] for d in rag_context if d.get("source")})
        if unique_sources:
            sources_block = "\n\n---\n**Sources:** " + " | ".join(unique_sources)

    return {"final_response": synthesis + sources_block}
