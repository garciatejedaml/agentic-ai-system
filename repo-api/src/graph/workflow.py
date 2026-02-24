"""
LangGraph workflow assembly.

Topology:
    START → intake → retrieve → strands → format → END

The graph is compiled once and reused across invocations.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src.graph.nodes import format_node, intake_node, retrieve_node, strands_node
from src.graph.state import AgentState


def build_graph() -> StateGraph:
    """Build and compile the LangGraph StateGraph."""
    graph = StateGraph(AgentState)

    # ── Register nodes ────────────────────────────────────────────────────────
    graph.add_node("intake", intake_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("strands", strands_node)   # ← Strands multi-agent group
    graph.add_node("format", format_node)

    # ── Edges (linear for POC) ────────────────────────────────────────────────
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "retrieve")
    graph.add_edge("retrieve", "strands")
    graph.add_edge("strands", "format")
    graph.add_edge("format", END)

    return graph.compile()


# ── Public helpers ────────────────────────────────────────────────────────────

_compiled_graph = None


def get_graph():
    """Return the singleton compiled graph."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def run_query(query: str) -> dict:
    """
    Convenience wrapper: run a query through the full graph.

    Automatically attaches the Langfuse callback handler when observability
    is enabled, enabling the graph view in the Langfuse UI.

    Returns the final AgentState dict.
    """
    from src.observability import get_langfuse_callback

    graph = get_graph()
    initial_state: AgentState = {
        "query": query,
        "rag_context": None,
        "research": None,
        "synthesis": None,
        "final_response": None,
        "error": None,
    }

    langfuse_cb = get_langfuse_callback()
    invoke_config = {"callbacks": [langfuse_cb]} if langfuse_cb else {}

    return graph.invoke(initial_state, config=invoke_config)
