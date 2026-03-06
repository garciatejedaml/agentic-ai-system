"""
Factory that returns a Strands-compatible model based on LLM_PROVIDER.

Local dev  (LLM_PROVIDER=anthropic) → LiteLLMModel via Anthropic API
Local free (LLM_PROVIDER=ollama)    → LiteLLMModel via Ollama (llama3.2, qwen2.5, etc.)
AWS prod   (LLM_PROVIDER=bedrock)   → BedrockModel (no API key — IAM role auth)
CI/infra   (LLM_PROVIDER=mock)      → LiteLLMModel with canned response (no LLM needed)

Tiered model strategy:
  get_strands_model()       → main model (Sonnet / larger Ollama model) for agent reasoning
  get_strands_fast_model()  → fast model (Haiku / smaller Ollama model) for tool-heavy sub-agents
"""
from src.config import config

_MOCK_RESPONSE = (
    "Mock LLM response: the Agentic AI System infrastructure is operational. "
    "All services are reachable and the agent pipeline executed successfully. "
    "Set LLM_PROVIDER=anthropic (or bedrock / ollama) to get real LLM responses."
)


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

    if config.LLM_PROVIDER == "mock":
        return LiteLLMModel(
            model_id="openai/gpt-3.5-turbo",
            params={"api_key": "mock-key", "mock_response": _MOCK_RESPONSE},
        )
    elif config.LLM_PROVIDER == "ollama":
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

    if config.LLM_PROVIDER == "mock":
        return LiteLLMModel(
            model_id="openai/gpt-3.5-turbo",
            params={"api_key": "mock-key", "mock_response": _MOCK_RESPONSE},
        )
    elif config.LLM_PROVIDER == "ollama":
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
            model_id=config.BEDROCK_FAST_MODEL,
            region_name=config.AWS_REGION,
        )
