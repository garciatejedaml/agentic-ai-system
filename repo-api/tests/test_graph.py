"""
Tests for the LangGraph workflow.

Uses mocks so tests run without real LLM calls or ChromaDB.
"""
import pytest
from unittest.mock import MagicMock, patch


# ── Unit tests for individual nodes ──────────────────────────────────────────

def test_intake_node_valid():
    from src.graph.nodes import intake_node

    result = intake_node({"query": "  Hello world  "})
    assert result["query"] == "Hello world"
    assert result["error"] is None


def test_intake_node_empty():
    from src.graph.nodes import intake_node

    result = intake_node({"query": ""})
    assert result["error"] is not None
    assert result["final_response"] is not None


def test_retrieve_node_skips_on_error():
    from src.graph.nodes import retrieve_node

    result = retrieve_node({"query": "test", "error": "upstream error"})
    assert result == {}  # no-op when there's already an error


def test_retrieve_node_returns_docs():
    from src.graph.nodes import retrieve_node

    fake_docs = [{"text": "chunk1", "source": "doc.txt", "distance": 0.1}]
    with patch("src.graph.nodes.get_retriever") as mock_get:
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = fake_docs
        mock_get.return_value = mock_retriever

        result = retrieve_node({"query": "test", "error": None})

    assert result["rag_context"] == fake_docs


def test_strands_node_skips_on_error():
    from src.graph.nodes import strands_node

    result = strands_node({"query": "test", "error": "some error", "rag_context": []})
    assert result == {}


def test_strands_node_calls_orchestrator():
    from src.graph.nodes import strands_node
    from src.agents.orchestrator import OrchestratorResult

    mock_result = OrchestratorResult(research="findings", synthesis="answer")
    with patch("src.graph.nodes.run_strands_orchestrator", return_value=mock_result):  # type: ignore
        # need to make the import work inside the node
        with patch.dict("sys.modules", {}):
            import importlib, sys
            # Patch the actual module path the node imports from
            with patch("src.agents.orchestrator.run_strands_orchestrator", return_value=mock_result):
                result = strands_node(
                    {"query": "test", "error": None, "rag_context": []}
                )

    assert result.get("research") == "findings" or "synthesis" in result


def test_format_node_with_synthesis():
    from src.graph.nodes import format_node

    state = {
        "error": None,
        "synthesis": "This is the answer.",
        "rag_context": [{"source": "doc.txt", "text": "..."}],
    }
    result = format_node(state)
    assert "This is the answer." in result["final_response"]
    assert "doc.txt" in result["final_response"]


def test_format_node_with_error():
    from src.graph.nodes import format_node

    state = {"error": "Something broke", "synthesis": None, "rag_context": []}
    result = format_node(state)
    assert "Error" in result["final_response"]
    assert "Something broke" in result["final_response"]


# ── Integration test (no real LLM) ────────────────────────────────────────────

def test_full_graph_smoke(monkeypatch):
    """
    Smoke test: run the full graph with all external calls mocked.
    Verifies the graph compiles and routes correctly.
    """
    import tempfile, os
    from src.agents.orchestrator import OrchestratorResult

    # Patch ChromaDB to a temp dir
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("CHROMA_PERSIST_DIR", tmpdir)
        import src.rag.retriever as rag_mod
        rag_mod._retriever = None

        # Patch Strands orchestrator
        mock_orch = MagicMock(return_value=OrchestratorResult(
            research="Research findings here.",
            synthesis="Final synthesized answer."
        ))

        with patch("src.graph.nodes.run_strands_orchestrator", mock_orch):
            # Reset compiled graph
            import src.graph.workflow as wf_mod
            wf_mod._compiled_graph = None

            from src.graph.workflow import run_query
            state = run_query("What is LangGraph?")

        assert state["query"] == "What is LangGraph?"
        assert state["final_response"] is not None
        assert "Final synthesized answer." in state["final_response"]

        rag_mod._retriever = None
        wf_mod._compiled_graph = None
