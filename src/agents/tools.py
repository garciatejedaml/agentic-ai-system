"""
Strands tools shared across agents.

Tools are plain functions decorated with @tool.
Each tool becomes available to any Strands Agent that receives it.
"""
from strands import tool

from src.rag.retriever import get_retriever


@tool
def search_knowledge_base(query: str) -> str:
    """
    Search the RAG knowledge base for information relevant to the query.

    Use this tool when you need to find factual information, context,
    or supporting evidence from the ingested documents.

    Args:
        query: The search query to find relevant information.

    Returns:
        Relevant text passages from the knowledge base.
    """
    retriever = get_retriever()

    if retriever.count() == 0:
        return "Knowledge base is empty. No documents have been ingested yet."

    results = retriever.retrieve(query)
    if not results:
        return f"No relevant information found for: {query}"

    formatted = []
    for i, doc in enumerate(results, 1):
        source = f" [source: {doc['source']}]" if doc["source"] else ""
        formatted.append(f"[{i}]{source}\n{doc['text']}")

    return "\n\n---\n\n".join(formatted)


@tool
def summarize_findings(findings: str) -> str:
    """
    Produce a concise bullet-point summary of raw research findings.

    Use this tool to condense verbose retrieved content into key points
    before passing to the synthesizer.

    Args:
        findings: Raw text containing research findings to summarize.

    Returns:
        A bullet-point summary of the key findings.
    """
    # In a real system this could call another model/process.
    # For the POC the orchestrating agent will handle summarization through
    # its own LLM reasoning; this tool is a placeholder showing the pattern.
    lines = [line.strip() for line in findings.split("\n") if line.strip()]
    bullets = "\n".join(f"• {line}" for line in lines[:20])
    return bullets or "No findings to summarize."
