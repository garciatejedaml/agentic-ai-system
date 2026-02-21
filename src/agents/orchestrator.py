"""
Strands Multi-Agent Orchestrator

This module is what LangGraph calls as a single node.
Internally it runs a two-agent pipeline:
  1. Researcher → searches RAG, produces findings
  2. Synthesizer → crafts the final answer from those findings

The orchestrator is intentionally kept simple for the POC.
In a real system you could add routing, parallelism, or more agents.
"""
from dataclasses import dataclass

from src.agents.researcher import create_researcher
from src.agents.synthesizer import create_synthesizer


@dataclass
class OrchestratorResult:
    research: str
    synthesis: str


def run_strands_orchestrator(query: str, rag_context: list[dict]) -> OrchestratorResult:
    """
    Entry point called from the LangGraph node.

    Args:
        query:       The original user question.
        rag_context: Pre-retrieved docs from the LangGraph RAG node
                     (list of {"text": ..., "source": ...}).

    Returns:
        OrchestratorResult with research and synthesis strings.
    """
    # ── Step 1: Research ─────────────────────────────────────────────────────
    researcher = create_researcher()

    # We pass pre-retrieved context so the researcher can complement it
    # with its own tool calls if needed.
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
    research_response = researcher(research_prompt)
    research_text = str(research_response)

    # ── Step 2: Synthesize ───────────────────────────────────────────────────
    synthesizer = create_synthesizer()

    synthesis_prompt = (
        f"Original question: {query}\n\n"
        f"Research findings:\n{research_text}\n\n"
        "Please synthesize a clear, structured answer."
    )
    synthesis_response = synthesizer(synthesis_prompt)
    synthesis_text = str(synthesis_response)

    return OrchestratorResult(research=research_text, synthesis=synthesis_text)
