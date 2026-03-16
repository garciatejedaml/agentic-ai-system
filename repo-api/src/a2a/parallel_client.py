"""
Parallel A2A Client — Phase 3

Calls multiple A2A agent services concurrently using asyncio.gather.
Each agent is driven by an AgentConfig that carries its own timeout_ms and
priority (required | optional).

Errors from individual agents are captured as AgentResult(success=False) —
never raised — so partial results from healthy agents are always preserved.

Usage:
    from src.agents.llm_router import AgentConfig
    configs = [
        AgentConfig(id="kdb-agent",      priority="required", timeout_ms=90000),
        AgentConfig(id="risk-pnl-agent", priority="optional", timeout_ms=30000),
    ]
    results = call_agents_parallel_sync(configs, query)
    # {"kdb-agent": AgentResult(success=True, ...), "risk-pnl-agent": AgentResult(...)}
"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.a2a.client import call_agent
from src.a2a.registry import get_endpoint

if TYPE_CHECKING:
    from src.agents.llm_router import AgentConfig


@dataclass
class AgentResult:
    """Result from a single A2A agent call, including execution metadata."""
    agent_id: str
    text: str
    success: bool
    priority: str          # "required" | "optional"
    duration_ms: float
    timed_out: bool = False
    error: str = field(default="", repr=False)


async def call_agents_parallel(
    agent_configs: list["AgentConfig"],
    query: str,
) -> dict[str, AgentResult]:
    """
    Call multiple A2A agents concurrently, each with its own timeout and priority.

    Args:
        agent_configs: List of AgentConfig (id, priority, timeout_ms per agent)
        query:         Natural language query forwarded to each agent

    Returns:
        Dict mapping agent_id → AgentResult.
        Failed or timed-out agents return AgentResult(success=False) — never raised.
    """
    from src.config import config

    async def _call_one(ac: "AgentConfig") -> AgentResult:
        endpoint = get_endpoint(ac.id, config.get_agent_url(ac.id))
        timeout_s = ac.timeout_ms / 1000.0
        t0 = time.monotonic()
        try:
            text = await call_agent(endpoint, query, timeout=int(timeout_s))
            duration_ms = (time.monotonic() - t0) * 1000
            # call_agent never raises — error responses come back as descriptive strings
            is_error = (
                text.startswith(f"[{ac.id} error")
                or "timed out" in text
                or "unreachable" in text
            )
            timed_out = "timed out" in text
            return AgentResult(
                agent_id=ac.id,
                text=text,
                success=not is_error,
                priority=ac.priority,
                duration_ms=round(duration_ms, 1),
                timed_out=timed_out,
                error=text if is_error else "",
            )
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return AgentResult(
                agent_id=ac.id,
                text=f"[{ac.id} error: {exc}]",
                success=False,
                priority=ac.priority,
                duration_ms=round(duration_ms, 1),
                error=str(exc),
            )

    tasks = [_call_one(ac) for ac in agent_configs]
    outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    results: dict[str, AgentResult] = {}
    for ac, outcome in zip(agent_configs, outcomes):
        if isinstance(outcome, Exception):
            results[ac.id] = AgentResult(
                agent_id=ac.id,
                text=f"[{ac.id} error: {outcome}]",
                success=False,
                priority=ac.priority,
                duration_ms=0.0,
                error=str(outcome),
            )
        else:
            results[ac.id] = outcome
    return results


def call_agents_parallel_sync(
    agent_configs: list["AgentConfig"],
    query: str,
) -> dict[str, AgentResult]:
    """Synchronous wrapper for use inside the LangGraph node (sync context)."""
    return asyncio.run(call_agents_parallel(agent_configs, query))
