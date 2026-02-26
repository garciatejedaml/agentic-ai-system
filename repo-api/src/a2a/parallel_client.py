"""
Parallel A2A Client — Phase 3

Calls multiple A2A agent services concurrently using asyncio.gather.
Errors from individual agents are returned as strings (never raised),
preserving partial results from healthy agents.

Usage:
    results = call_agents_parallel_sync(["kdb-agent", "portfolio-agent"], query)
    # returns {"kdb-agent": "...", "portfolio-agent": "..."}
"""
import asyncio

from src.a2a.client import call_agent
from src.a2a.registry import get_endpoint


async def call_agents_parallel(
    agent_ids: list[str],
    query: str,
    timeout: int = 120,
) -> dict[str, str]:
    """
    Call multiple A2A agents concurrently.

    Args:
        agent_ids: List of agent IDs to call (e.g. ["kdb-agent", "etf-agent"])
        query:     Natural language query forwarded to each agent
        timeout:   Max seconds per agent call

    Returns:
        Dict mapping agent_id → result text. Failed agents return error strings.
    """
    from src.config import config

    async def _call_one(agent_id: str) -> tuple[str, str]:
        endpoint = get_endpoint(agent_id, config.get_agent_url(agent_id))
        result = await call_agent(endpoint, query, timeout=timeout)
        return agent_id, result

    tasks = [_call_one(agent_id) for agent_id in agent_ids]
    outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    results: dict[str, str] = {}
    for agent_id, outcome in zip(agent_ids, outcomes):
        if isinstance(outcome, Exception):
            results[agent_id] = f"[{agent_id} error: {outcome}]"
        else:
            _, text = outcome
            results[agent_id] = text
    return results


def call_agents_parallel_sync(
    agent_ids: list[str],
    query: str,
    timeout: int = 120,
) -> dict[str, str]:
    """Synchronous wrapper for use inside the LangGraph node (sync context)."""
    return asyncio.run(call_agents_parallel(agent_ids, query, timeout))
