"""
Factory that returns a Strands-compatible model based on LLM_PROVIDER.

Local dev  (LLM_PROVIDER=anthropic) → uses LiteLLMModel via Anthropic API
AWS prod   (LLM_PROVIDER=bedrock)   → uses BedrockModel
"""
from src.config import config


def get_strands_model():
    """Return a configured Strands model for the current environment."""
    if config.is_local():
        # LiteLLM bridges Strands → Anthropic API (no Bedrock needed locally)
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
