"""
Synthesizer Agent (Strands)

Responsibility: Take research findings and craft a clear, user-facing answer.
No tool access — pure reasoning over the provided context.
"""
from strands import Agent

from src.agents.model_factory import get_strands_model

SYNTHESIZER_SYSTEM_PROMPT = """You are an expert communicator and analyst.

You receive:
- The original user question
- Research findings from a research agent

Your job:
1. Synthesize the findings into a clear, concise answer.
2. Structure the response with:
   - A direct answer to the question (1-2 sentences)
   - Supporting details (bullet points or short paragraphs)
   - Confidence level: HIGH / MEDIUM / LOW based on evidence quality
3. Use plain language. Avoid jargon unless the user's question uses it.
4. If the research found gaps, acknowledge them honestly.
"""


def create_synthesizer() -> Agent:
    """Instantiate the Synthesizer Strands agent (no tools — reasoning only)."""
    return Agent(
        model=get_strands_model(),
        system_prompt=SYNTHESIZER_SYSTEM_PROMPT,
        tools=[],
    )
