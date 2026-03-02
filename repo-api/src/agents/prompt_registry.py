"""
Langfuse Prompt Registry

Decouples agent system prompts from Python code. Prompts are stored and
versioned in Langfuse, editable without a code deployment.

Self-seeding: on the first call with a given prompt name, if it doesn't
exist in Langfuse yet, the provided default is used AND created there —
so subsequent restarts (and other replicas) load the canonical version.

Graceful degradation:
  - OBSERVABILITY_ENABLED=false → always returns default (no Langfuse call)
  - Langfuse unreachable → logs warning, returns default
  - Prompt not found after seeding attempt → returns default

Usage in agents:
    from src.agents.prompt_registry import get_system_prompt

    _SYSTEM_PROMPT_DEFAULT = \"\"\"...hardcoded fallback...\"\"\"

    def run_my_agent(query: str) -> str:
        system_prompt = get_system_prompt("my-agent-system-prompt", _SYSTEM_PROMPT_DEFAULT)
        agent = Agent(model=..., system_prompt=system_prompt, ...)
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

# ── Singleton Langfuse client ─────────────────────────────────────────────────
_client = None
_client_lock = threading.Lock()
_prompt_cache: dict[str, str] = {}


def _get_client():
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        try:
            from src.config import config
            if not config.OBSERVABILITY_ENABLED:
                return None
            if not config.LANGFUSE_PUBLIC_KEY or not config.LANGFUSE_SECRET_KEY:
                return None
            from langfuse import Langfuse
            _client = Langfuse(
                public_key=config.LANGFUSE_PUBLIC_KEY,
                secret_key=config.LANGFUSE_SECRET_KEY,
                host=config.LANGFUSE_HOST or "https://cloud.langfuse.com",
            )
            logger.info("[prompt_registry] Langfuse client initialized → %s", config.LANGFUSE_HOST)
        except Exception as exc:
            logger.warning("[prompt_registry] Langfuse init failed — prompts will use defaults: %s", exc)
            _client = None
    return _client


def get_system_prompt(name: str, default: str) -> str:
    """
    Load a system prompt from Langfuse by name.

    Returns the compiled prompt text. Falls back to `default` if Langfuse
    is disabled, unreachable, or the prompt doesn't exist yet (first run:
    also seeds the prompt in Langfuse from `default`).

    Args:
        name:    Prompt name in Langfuse (e.g. "amps-agent-system-prompt").
        default: Hardcoded fallback and initial value for self-seeding.
    """
    # Fast path: already cached in this process
    if name in _prompt_cache:
        return _prompt_cache[name]

    client = _get_client()
    if client is None:
        return default

    # ── Try to load from Langfuse ─────────────────────────────────────────────
    try:
        prompt_obj = client.get_prompt(name, label="production", cache_ttl_seconds=300)
        text = prompt_obj.compile()
        _prompt_cache[name] = text
        logger.info("[prompt_registry] Loaded prompt '%s' from Langfuse", name)
        return text
    except Exception:
        pass  # prompt may not exist yet — fall through to seed

    # ── Self-seed: create the prompt in Langfuse from the default ────────────
    try:
        client.create_prompt(
            name=name,
            prompt=default,
            labels=["production"],
            config={"source": "auto-seeded"},
        )
        logger.info("[prompt_registry] Seeded prompt '%s' in Langfuse (first run)", name)
    except Exception as exc:
        logger.warning("[prompt_registry] Could not seed prompt '%s': %s", name, exc)

    # Use default for this run; next restart will load from Langfuse
    return default
