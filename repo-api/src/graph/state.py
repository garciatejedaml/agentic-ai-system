"""LangGraph shared state definition."""
from __future__ import annotations

from typing import List, Optional
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """
    State passed between LangGraph nodes.

    Fields are populated progressively as the graph executes:

        intake_node  → sets `query`
        retrieve_node → sets `rag_context`
        strands_node  → sets `research`, `synthesis`
        format_node   → sets `final_response`
    """
    # Input
    query: str

    # After RAG retrieval
    rag_context: Optional[List[dict]]   # [{"text": ..., "source": ..., "distance": ...}]

    # After Strands agents
    research: Optional[str]
    synthesis: Optional[str]

    # Final output
    final_response: Optional[str]

    # Optional: error message if a node fails
    error: Optional[str]
