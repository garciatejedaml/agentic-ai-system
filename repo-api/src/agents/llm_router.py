"""
LLM Router — Phase 3

Replaces the financial-orchestrator as the routing layer.
Uses a single structured Haiku completion call (no agent loop) to decide
which specialist agents to call and whether to call them in parallel or
sequentially.

Each agent in the routing plan carries:
  - id:          agent identifier (matches DynamoDB registry)
  - priority:    "required" | "optional"
                   required → answer depends on this agent's data
                   optional → enriches the answer; query is still answerable without it
  - timeout_ms:  per-agent deadline (overrides config defaults)

The router reads the DynamoDB registry at call time so new agents are
discovered automatically without code changes.

Usage:
    decision = route_query("dame el VaR del portfolio HY_MAIN")
    # RouterDecision(agents=[AgentConfig(id="risk-pnl-agent", priority="required", timeout_ms=90000)], ...)

    decision = route_query("exposure en HY bonds y flujos de ETFs")
    # RouterDecision(agents=[AgentConfig("portfolio-agent", ...), AgentConfig("etf-agent", ...)], ...)
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

# Fallback when DynamoDB is empty or router fails
_FALLBACK_AGENT = "kdb-agent"

# Default timeouts per agent (ms) — used when the LLM doesn't specify timeout_ms
_AGENT_DEFAULT_TIMEOUT_MS: dict[str, int] = {
    "kdb-agent":              90000,   # large parquet scans
    "amps-agent":             30000,   # real-time pub/sub — must be fast
    "portfolio-agent":        60000,
    "cds-agent":              60000,
    "etf-agent":              60000,
    "risk-pnl-agent":         90000,   # VaR is CPU-intensive
    "financial-orchestrator": 90000,
}

# Static descriptions shown when DynamoDB returns no capabilities
_AGENT_DESCRIPTIONS = {
    "kdb-agent":         "Historical Bond RFQ analytics: trader rankings, hit rates, spreads, desk performance (HY/IG/EM/RATES), 6-month history",
    "amps-agent":        "Live real-time AMPS data (State-of-World): current orders, live positions, market quotes, intraday P&L, portfolio NAV (portfolio_nav topic), CDS spreads tick-by-tick (cds_spreads topic), ETF NAV and flows (etf_nav topic), VaR/DV01/CS01 risk metrics (risk_metrics topic). Use for 'ahora mismo', 'en tiempo real', 'actual', 'live', 'current' queries.",
    "portfolio-agent":   "Portfolio holdings and exposure: positions, weights, concentration, cost basis, duration by portfolio (HY_MAIN, IG_CORE, EM_BLEND, RATES_GOV, MULTI_STRAT)",
    "cds-agent":         "Credit Default Swap market data: CDS spreads by tenor (1/3/5/7/10y), term structures, credit curve screener for 50 entities",
    "etf-agent":         "ETF analytics: NAV, AUM, creation/redemption flows, basket composition, premium/discount for HY/IG/EM/RATES ETFs (HYG, LQD, JNK, etc.)",
    "risk-pnl-agent":    "Cross-cutting risk and P&L: VaR, DV01, CS01 computed from live portfolio positions + market spreads; P&L attribution by desk/trader",
    "financial-orchestrator": "Multi-source financial synthesis: combines KDB historical + AMPS live data for complex queries needing both sources",
}

_ROUTER_SYSTEM = """You are a query router for a financial data platform.
Your ONLY job is to select which specialist agents should handle a query.
Output valid JSON only — no explanation, no markdown, no other text."""

_ROUTER_PROMPT_TEMPLATE = """Available agents:
{agent_list}

User query: "{query}"

Rules:
- Select ONLY agents whose data is relevant to the query
- Use "parallel" when agents answer independent sub-questions simultaneously
- Use "sequential" ONLY for risk-pnl-agent (it needs portfolio + market data first)
- Default to kdb-agent for general bond/trader/desk questions
- For VaR, DV01, CS01, P&L attribution in real-time → include amps-agent (risk_metrics topic)
- For portfolio NAV/exposure in real-time → include amps-agent (portfolio_nav topic)
- For CDS spreads live/tick data → include amps-agent (cds_spreads topic)
- For ETF NAV/flows live → include amps-agent (etf_nav topic)
- For live/current/today/'ahora mismo'/'en tiempo real'/'actual' data → include amps-agent
- For historical analytics, rankings, 6-month trends → include kdb-agent

Priority rules:
- "required": the query cannot be answered without this agent's data
- "optional": enriches the answer but the query is still answerable without it

Timeout rules (use these defaults unless the query implies urgency):
- amps-agent: 30000ms (real-time, must be fast)
- kdb-agent: 90000ms (parquet scans can be slow)
- risk-pnl-agent: 90000ms (VaR computation is CPU-intensive)
- all others: 60000ms

Respond with JSON only:
{{"agents": [{{"id": "agent-id", "priority": "required", "timeout_ms": 60000}}], "strategy": "parallel", "reasoning": "one sentence why"}}"""


@dataclass
class AgentConfig:
    """Per-agent routing configuration emitted by the LLM Router."""
    id: str
    priority: Literal["required", "optional"] = "required"
    timeout_ms: int = 60000


@dataclass
class RouterDecision:
    agents: list[AgentConfig]
    strategy: Literal["parallel", "sequential"] = "parallel"
    reasoning: str = ""
    fallback_used: bool = field(default=False, repr=False)


def route_query(query: str) -> RouterDecision:
    """
    Use one Haiku completion call to decide which agents handle the query.

    Reads DynamoDB registry for active agents; falls back to static
    descriptions if registry is empty. Falls back to kdb-agent if the
    LLM response cannot be parsed.

    Args:
        query: The user's natural language question

    Returns:
        RouterDecision with AgentConfig list (each carrying priority + timeout_ms)
    """
    from src.config import config
    from src.a2a.registry import list_all_agents

    # Build agent description block from registry (with static fallback)
    try:
        active_agents = list_all_agents()
    except Exception as e:
        logger.warning("[llm-router] registry unavailable (%s), using static descriptions", e)
        active_agents = []
    if active_agents:
        agent_map = {
            a["agent_id"]: ", ".join(a.get("capabilities", []))
            for a in active_agents
            if a.get("agent_id") in _AGENT_DESCRIPTIONS
        }
        # Enrich with static descriptions for better routing quality
        agent_list = "\n".join(
            f'- "{aid}": {_AGENT_DESCRIPTIONS.get(aid, caps)}'
            for aid, caps in agent_map.items()
        )
    else:
        # DynamoDB not available — use static descriptions
        agent_list = "\n".join(
            f'- "{aid}": {desc}' for aid, desc in _AGENT_DESCRIPTIONS.items()
        )

    prompt = _ROUTER_PROMPT_TEMPLATE.format(
        agent_list=agent_list,
        query=query,
    )

    # Mock mode: skip LLM call entirely — route to kdb-agent as default
    if config.LLM_PROVIDER == "mock":
        print("[LLM Router] mock mode → kdb-agent (no LLM call)")
        return RouterDecision(
            agents=[AgentConfig(id=_FALLBACK_AGENT)],
            strategy="parallel",
            reasoning="mock",
        )

    try:
        import litellm

        if config.LLM_PROVIDER == "ollama":
            ollama_model = config.OLLAMA_FAST_MODEL or config.OLLAMA_MODEL
            response = litellm.completion(
                model=f"ollama/{ollama_model}",
                messages=[
                    {"role": "system", "content": _ROUTER_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                api_base=config.OLLAMA_BASE_URL,
                api_key="ollama",
                max_tokens=512,
                temperature=0,
                format="json",
            )
        else:
            response = litellm.completion(
                model=f"anthropic/{config.ANTHROPIC_FAST_MODEL}",
                messages=[
                    {"role": "system", "content": _ROUTER_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                api_key=config.ANTHROPIC_API_KEY,
                max_tokens=512,
                temperature=0,
            )
        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences that Haiku may wrap around JSON
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:]).strip()
        decision = json.loads(raw)

        agents = _parse_agents(decision.get("agents", []))
        strategy = decision.get("strategy", "parallel")
        reasoning = decision.get("reasoning", "")

        logger.info(
            "[llm-router] agents=%s strategy=%s reasoning=%s",
            [(a.id, a.priority) for a in agents], strategy, reasoning,
        )
        print(f"[LLM Router] → agents={[(a.id, a.priority) for a in agents]} strategy={strategy}")

        return RouterDecision(agents=agents, strategy=strategy, reasoning=reasoning)

    except Exception as e:
        logger.warning("[llm-router] fallback to %s due to error: %s", _FALLBACK_AGENT, e)
        print(f"[LLM Router] fallback → {_FALLBACK_AGENT} (error: {e})")
        return RouterDecision(
            agents=[AgentConfig(id=_FALLBACK_AGENT)],
            strategy="parallel",
            reasoning="fallback",
            fallback_used=True,
        )


def _parse_agents(raw_agents: list) -> list[AgentConfig]:
    """
    Parse the agents field from the LLM response.

    Handles both the new format (list of objects with id/priority/timeout_ms)
    and the old format (list of strings) for backward compatibility.
    Validates agent IDs against the known set and falls back to kdb-agent if empty.
    """
    known = set(_AGENT_DESCRIPTIONS.keys())
    configs: list[AgentConfig] = []

    for item in raw_agents:
        if isinstance(item, str):
            # Old format: "kdb-agent"
            agent_id = item
            if agent_id not in known:
                continue
            configs.append(AgentConfig(
                id=agent_id,
                priority="required",
                timeout_ms=_AGENT_DEFAULT_TIMEOUT_MS.get(agent_id, 60000),
            ))
        elif isinstance(item, dict):
            # New format: {"id": "kdb-agent", "priority": "required", "timeout_ms": 90000}
            agent_id = item.get("id", "")
            if agent_id not in known:
                continue
            priority = item.get("priority", "required")
            if priority not in ("required", "optional"):
                priority = "required"
            timeout_ms = item.get("timeout_ms", _AGENT_DEFAULT_TIMEOUT_MS.get(agent_id, 60000))
            configs.append(AgentConfig(id=agent_id, priority=priority, timeout_ms=int(timeout_ms)))

    return configs or [AgentConfig(id=_FALLBACK_AGENT)]
