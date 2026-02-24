"""
LangGraph node functions.

Each function receives the current AgentState and returns a dict with
the fields it wants to update. LangGraph merges the returned dict into state.

Graph topology:
    intake_node → retrieve_node → strands_node → format_node → END
"""
from __future__ import annotations

import traceback

from src.graph.state import AgentState
from src.rag.retriever import get_retriever


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
    Query ChromaDB and attach the top-k relevant document chunks to state.
    This runs *before* the Strands agents so they receive pre-fetched context.
    """
    if state.get("error"):
        return {}

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

    try:
        # Import here to avoid circular deps and keep startup fast
        from src.agents.orchestrator import run_strands_orchestrator

        result = run_strands_orchestrator(
            query=state["query"],
            rag_context=state.get("rag_context") or [],
        )
        return {"research": result.research, "synthesis": result.synthesis}
    except Exception as exc:
        tb = traceback.format_exc()
        return {"error": f"Strands agents failed: {exc}\n{tb}"}


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
