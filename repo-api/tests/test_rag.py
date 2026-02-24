"""Tests for the RAG retriever module."""
import pytest
import tempfile
import os
from pathlib import Path


@pytest.fixture
def temp_chroma(monkeypatch):
    """Use a temporary directory for ChromaDB during tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("CHROMA_PERSIST_DIR", tmpdir)
        # Reset singleton
        import src.rag.retriever as rag_mod
        rag_mod._retriever = None
        yield tmpdir
        rag_mod._retriever = None


def test_add_and_retrieve(temp_chroma):
    from src.rag.retriever import RAGRetriever

    r = RAGRetriever()
    assert r.count() == 0

    r.add_texts(
        ["LangGraph is a graph-based orchestration framework."],
        metadatas=[{"source": "test"}],
    )
    assert r.count() == 1

    results = r.retrieve("orchestration framework", k=1)
    assert len(results) == 1
    assert "LangGraph" in results[0]["text"]
    assert results[0]["source"] == "test"


def test_add_file(temp_chroma, tmp_path):
    from src.rag.retriever import RAGRetriever

    doc = tmp_path / "test.txt"
    doc.write_text("Strands is an AWS agent framework. " * 20)

    r = RAGRetriever()
    n = r.add_file(doc)
    assert n > 0
    assert r.count() == n

    results = r.retrieve("AWS agent")
    assert len(results) > 0
    assert "Strands" in results[0]["text"]


def test_empty_retrieval(temp_chroma):
    from src.rag.retriever import RAGRetriever

    r = RAGRetriever()
    # count=0, should return empty list without crashing
    results = r.retrieve("anything")
    assert results == []


def test_chunk_text():
    from src.rag.retriever import RAGRetriever

    text = "word " * 300  # 1500 chars
    chunks = RAGRetriever._chunk_text(text, chunk_size=500)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 500 + 10  # small tolerance for word boundaries
