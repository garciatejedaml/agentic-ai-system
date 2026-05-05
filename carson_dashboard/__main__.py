"""Standalone entrypoint: `python -m carson_dashboard`.

Boots a FastAPI app with seeded historical data and a live simulator.
When wiring to real Carson, mount routes.router into Carson's existing
FastAPI app instead of running this.
"""

from __future__ import annotations

import asyncio

import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from . import agent_rooms, audit, autonomous, chats, db, ops_db, pm, simulator
from .routes import router, mount_static


def create_app(seed: bool = True, simulate: bool = True) -> FastAPI:
    db.init_db()
    ops_db.init_ops_db()
    autonomous.init_autonomous_db()
    audit.init_audit_db()
    chats.init_chat_db()
    pm.init_pm_db()
    agent_rooms.init_rooms_db()
    if seed:
        simulator.seed_history()
        simulator.seed_ops_history()
        autonomous.seed_demo_state()
        simulator.seed_audit_history()
        simulator.seed_chat_sessions()
        pm.seed_demo()
        agent_rooms.seed_demo_rooms()

    app = FastAPI(title="Carson dashboard")
    app.include_router(router)
    mount_static(app)

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("/dashboard")

    if simulate:
        @app.on_event("startup")
        async def _start_sim():
            asyncio.create_task(simulator.live_loop(interval=8.0))
            asyncio.create_task(simulator.ops_live_loop(interval=5.0))

    return app


if __name__ == "__main__":
    uvicorn.run(create_app(), host="127.0.0.1", port=8765, log_level="info")
