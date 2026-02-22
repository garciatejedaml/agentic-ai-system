"""Central configuration loaded from environment variables."""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Provider
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic")

    # Anthropic (local)
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")

    # Bedrock (AWS)
    AWS_REGION: str = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    BEDROCK_MODEL: str = os.getenv(
        "BEDROCK_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    )

    # RAG
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", ".chroma_db")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "4"))

    # MCP External Servers
    BRAVE_API_KEY: str = os.getenv("BRAVE_API_KEY", "")
    MCP_FILESYSTEM_PATH: str = os.getenv("MCP_FILESYSTEM_PATH", "./data")

    # Observability (Langfuse + Phoenix)
    OBSERVABILITY_ENABLED: bool = os.getenv("OBSERVABILITY_ENABLED", "false").lower() == "true"

    # Langfuse (graph view + metrics dashboard)
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

    # Phoenix / Arize (RAG + span analysis)
    PHOENIX_ENDPOINT: str = os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006")

    # Debug
    LANGGRAPH_DEBUG: bool = os.getenv("LANGGRAPH_DEBUG", "false").lower() == "true"

    @classmethod
    def is_local(cls) -> bool:
        return cls.LLM_PROVIDER == "anthropic"

    @classmethod
    def validate(cls) -> None:
        if cls.is_local() and not cls.ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic. "
                "Copy .env.example to .env and set your key."
            )


config = Config()
