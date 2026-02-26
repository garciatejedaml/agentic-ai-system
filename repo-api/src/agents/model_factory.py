"""
Factory that returns a Strands-compatible model based on LLM_PROVIDER.

Local dev  (LLM_PROVIDER=anthropic) → LiteLLMModel via Anthropic API
Local free (LLM_PROVIDER=ollama)    → LiteLLMModel via Ollama (llama3.2, qwen2.5, etc.)
AWS prod   (LLM_PROVIDER=bedrock)   → BedrockModel

Tiered model strategy:
  get_strands_model()       → main model (Sonnet / larger Ollama model) for agent reasoning
  get_strands_fast_model()  → fast model (Haiku / smaller Ollama model) for tool-heavy sub-agents
"""
from src.config import config


def _ollama_params(model: str) -> dict:
    """Build LiteLLM params dict for an Ollama model."""
    return {
        "api_base": config.OLLAMA_BASE_URL,
        # LiteLLM requires a non-empty api_key even for local Ollama
        "api_key": "ollama",
    }


def get_strands_model():
    """Return the main model — used for orchestrators and synthesizers."""
    from strands.models.litellm import LiteLLMModel  # type: ignore

    if config.LLM_PROVIDER == "ollama":
        model = config.OLLAMA_MODEL
        return LiteLLMModel(
            model_id=f"ollama/{model}",
            params=_ollama_params(model),
        )
    elif config.LLM_PROVIDER == "anthropic":
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
    """Return the fast model — used for sub-agents (KDB, AMPS) that mostly call tools."""
    from strands.models.litellm import LiteLLMModel  # type: ignore

    if config.LLM_PROVIDER == "ollama":
        # Use OLLAMA_FAST_MODEL if set, otherwise fall back to OLLAMA_MODEL
        model = config.OLLAMA_FAST_MODEL or config.OLLAMA_MODEL
        return LiteLLMModel(
            model_id=f"ollama/{model}",
            params=_ollama_params(model),
        )
    elif config.LLM_PROVIDER == "anthropic":
        return LiteLLMModel(
            model_id=f"anthropic/{config.ANTHROPIC_FAST_MODEL}",
            params={"api_key": config.ANTHROPIC_API_KEY},
        )
    else:
        from strands.models import BedrockModel  # type: ignore

        return BedrockModel(
            model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            region_name=config.AWS_REGION,
        )
