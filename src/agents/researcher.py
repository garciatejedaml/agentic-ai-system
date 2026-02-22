"""
Researcher Agent (Strands)

Responsibility: Given a user query + optional initial context,
search the knowledge base and produce structured research findings.
Optionally receives MCP tools (web search, fetch, filesystem) from the
orchestrator so it can go beyond the local RAG when needed.
"""
from strands import Agent

from src.agents.model_factory import get_strands_model
from src.agents.tools import search_knowledge_base, summarize_findings

RESEARCHER_SYSTEM_PROMPT = """You are a precise research assistant with access to multiple sources.

Your job:
1. Receive a question or topic to investigate.
2. Search the local knowledge base first using `search_knowledge_base`.
3. If local results are insufficient, use web search tools (brave_web_search)
   to find up-to-date information from the internet.
4. Use `fetch` to retrieve and read the content of specific URLs when needed.
5. Use filesystem tools to read local documents directly when relevant.
6. Use the `summarize_findings` tool to distill what you find.
7. Return a structured research report with:
   - Key facts found
   - Sources referenced (URLs, document names)
   - Gaps or uncertainties in the available information

Be factual. Clearly distinguish between local knowledge base results and
web/external sources. If no information is found anywhere, say so clearly.
"""


def create_researcher(extra_tools: list | None = None) -> Agent:
    """
    Instantiate the Researcher Strands agent.

    Args:
        extra_tools: Optional list of MCP-backed tools (web search, fetch,
                     filesystem) returned by `open_mcp_tools()`.
    """
    tools = [search_knowledge_base, summarize_findings]
    if extra_tools:
        tools.extend(extra_tools)

    return Agent(
        model=get_strands_model(),
        system_prompt=RESEARCHER_SYSTEM_PROMPT,
        tools=tools,
    )
