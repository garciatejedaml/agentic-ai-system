"""
Factory that returns a Strands-compatible model based on LLM_PROVIDER.

Local dev  (LLM_PROVIDER=anthropic) → uses LiteLLMModel via Anthropic API
AWS prod   (LLM_PROVIDER=bedrock)   → uses BedrockModel

Tiered model strategy (reduces cost ~10-20x on multi-agent runs):
  get_strands_model()       → ANTHROPIC_MODEL (default: sonnet) for orchestrators
  get_strands_fast_model()  → ANTHROPIC_FAST_MODEL (default: haiku) for sub-agents
"""
from src.config import config


def get_strands_model():
    """Return the main model (Sonnet) — used for orchestrators and synthesizers."""
    if config.is_local():
        from strands.models.litellm import LiteLLMModel  # type: ignore

        return LiteLLMModel(
            model_id=f"anthropic/{config.ANTHROPIC_MODEL}",
            params={"api_key": config.ANTHROPIC_API_KEY},
        )
    else:
        from strands.models import BedrockModel  # type: ignore

        return BedrockModel(
            model_id=config.BEDROCK_MODEL,
            region_name=config.AWS_REGION,
        )


def get_strands_fast_model():
    """Return the fast/cheap model (Haiku) — used for sub-agents (KDB, AMPS).

    These agents primarily call MCP tools and format results; they don't need
    the reasoning depth of Sonnet.  Haiku is ~20x cheaper per token.
    """
    if config.is_local():
        from strands.models.litellm import LiteLLMModel  # type: ignore

        return LiteLLMModel(
            model_id=f"anthropic/{config.ANTHROPIC_FAST_MODEL}",
            params={"api_key": config.ANTHROPIC_API_KEY},
        )
    else:
        from strands.models import BedrockModel  # type: ignore

        # Haiku on Bedrock
        return BedrockModel(
            model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            region_name=config.AWS_REGION,
        )
