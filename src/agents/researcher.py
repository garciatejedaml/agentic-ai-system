"""
Researcher Agent (Strands)

Responsibility: Given a user query + optional initial context,
search the knowledge base and produce structured research findings.
"""
from strands import Agent

from src.agents.model_factory import get_strands_model
from src.agents.tools import search_knowledge_base, summarize_findings

RESEARCHER_SYSTEM_PROMPT = """You are a precise research assistant.

Your job:
1. Receive a question or topic to investigate.
2. Use the `search_knowledge_base` tool to find relevant information.
3. Use the `summarize_findings` tool to distill what you find.
4. Return a structured research report with:
   - Key facts found
   - Sources referenced
   - Gaps or uncertainties in the available information

Be factual. Do not invent information not found in the knowledge base.
If the knowledge base lacks information, say so clearly.
"""


def create_researcher() -> Agent:
    """Instantiate the Researcher Strands agent."""
    return Agent(
        model=get_strands_model(),
        system_prompt=RESEARCHER_SYSTEM_PROMPT,
        tools=[search_knowledge_base, summarize_findings],
    )
