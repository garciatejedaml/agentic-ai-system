"""Glue between Carson's LangGraph and the dashboard.

Currently used by the simulator. When wired to real Carson, replace the
calls inside `wrap_langgraph` with LangGraph's callback hooks
(`on_chain_start`, `on_chain_end`, `on_tool_*`, etc.).
"""

from __future__ import annotations

import time
from typing import Any

from . import db
from .stream import bus


def record_run_start(run: dict[str, Any]) -> None:
    db.insert_run(run)
    bus.publish({"type": "run.start", "run": run})


def record_run_end(run_id: str, status: str, total_tokens: int = 0,
                   cost_usd: float = 0.0) -> None:
    db.update_run(
        run_id,
        ended_at=time.time(),
        status=status,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
    )
    bus.publish({
        "type": "run.end",
        "run_id": run_id,
        "status": status,
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
    })


def record_step(step: dict[str, Any]) -> int:
    step_id = db.insert_step(step)
    bus.publish({"type": "step", "step_id": step_id, **step})
    return step_id


def record_tool_call(call: dict[str, Any]) -> None:
    db.insert_tool_call(call)
    bus.publish({"type": "tool_call", **call})


def wrap_langgraph(graph: Any) -> Any:
    """Placeholder for the real integration.

    When connected to Carson on the VDI:
        from langchain_core.callbacks import BaseCallbackHandler
        class CarsonHandler(BaseCallbackHandler): ...
        return graph.with_config(callbacks=[CarsonHandler()])
    """
    return graph
