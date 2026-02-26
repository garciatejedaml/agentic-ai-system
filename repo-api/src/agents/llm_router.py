"""
LLM Router — Phase 3

Replaces the financial-orchestrator as the routing layer.
Uses a single structured Haiku completion call (no agent loop) to decide
which specialist agents to call and whether to call them in parallel or
sequentially.

The router reads the DynamoDB registry at call time so new agents are
discovered automatically without code changes.

Usage:
    decision = route_query("dame el VaR del portfolio HY_MAIN")
    # RouterDecision(agents=["risk-pnl-agent"], strategy="sequential", ...)

    decision = route_query("exposure en HY bonds y flujos de ETFs")
    # RouterDecision(agents=["portfolio-agent", "etf-agent"], strategy="parallel", ...)
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

# Fallback when DynamoDB is empty or router fails
_FALLBACK_AGENT = "kdb-agent"

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

Respond with JSON only:
{{"agents": ["agent-id-1"], "strategy": "parallel", "reasoning": "one sentence why"}}"""


@dataclass
class RouterDecision:
    agents: list[str]
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
        RouterDecision with agents list and parallel/sequential strategy
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

    try:
        import litellm

        response = litellm.completion(
            model=f"anthropic/{config.ANTHROPIC_FAST_MODEL}",
            messages=[
                {"role": "system", "content": _ROUTER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            api_key=config.ANTHROPIC_API_KEY,
            max_tokens=256,
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences that Haiku may wrap around JSON
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:]).strip()
        decision = json.loads(raw)

        agents = decision.get("agents", [_FALLBACK_AGENT])
        strategy = decision.get("strategy", "parallel")
        reasoning = decision.get("reasoning", "")

        # Validate agent IDs against known list
        known = set(_AGENT_DESCRIPTIONS.keys())
        agents = [a for a in agents if a in known] or [_FALLBACK_AGENT]

        logger.info(
            "[llm-router] agents=%s strategy=%s reasoning=%s",
            agents, strategy, reasoning,
        )
        print(f"[LLM Router] → agents={agents} strategy={strategy}")

        return RouterDecision(agents=agents, strategy=strategy, reasoning=reasoning)

    except Exception as e:
        logger.warning("[llm-router] fallback to %s due to error: %s", _FALLBACK_AGENT, e)
        print(f"[LLM Router] fallback → {_FALLBACK_AGENT} (error: {e})")
        return RouterDecision(
            agents=[_FALLBACK_AGENT],
            strategy="parallel",
            reasoning="fallback",
            fallback_used=True,
        )
