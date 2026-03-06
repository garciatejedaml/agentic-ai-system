"""Central configuration loaded from environment variables."""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Provider: "anthropic" | "bedrock" | "ollama" | "mock"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic")

    # Anthropic (local)
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
    # Fast/cheap model for sub-agents (KDB, AMPS) that mostly call tools
    ANTHROPIC_FAST_MODEL: str = os.getenv("ANTHROPIC_FAST_MODEL", "claude-haiku-4-5")

    # Ollama (free local LLM — no API key required)
    # Base URL when Ollama runs natively on Mac: http://host.docker.internal:11434
    # Base URL when Ollama runs in Docker:       http://ollama:11434
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    # If blank, uses OLLAMA_MODEL for both routing and agent reasoning
    OLLAMA_FAST_MODEL: str = os.getenv("OLLAMA_FAST_MODEL", "")

    # Bedrock (AWS — no API key needed, uses IAM role)
    AWS_REGION: str = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    BEDROCK_MODEL: str = os.getenv(
        "BEDROCK_MODEL", "us.anthropic.claude-sonnet-4-6-20251101-v1:0"
    )
    BEDROCK_FAST_MODEL: str = os.getenv(
        "BEDROCK_FAST_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    )

    # RAG — OpenSearch backend
    OPENSEARCH_URL: str = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
    OPENSEARCH_INDEX: str = os.getenv("OPENSEARCH_INDEX", "knowledge_base")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "4"))

    # MCP External Servers
    BRAVE_API_KEY: str = os.getenv("BRAVE_API_KEY", "")
    MCP_FILESYSTEM_PATH: str = os.getenv("MCP_FILESYSTEM_PATH", "./data")

    # AMPS (60East Technologies pub/sub)
    AMPS_ENABLED: bool = os.getenv("AMPS_ENABLED", "false").lower() == "true"
    AMPS_HOST: str = os.getenv("AMPS_HOST", "localhost")
    AMPS_PORT: int = int(os.getenv("AMPS_PORT", "9007"))
    AMPS_ADMIN_PORT: int = int(os.getenv("AMPS_ADMIN_PORT", "8085"))
    AMPS_CLIENT_NAME: str = os.getenv("AMPS_CLIENT_NAME", "agentic-ai-system")

    # KDB+ historical data store
    KDB_ENABLED: bool = os.getenv("KDB_ENABLED", "false").lower() == "true"
    KDB_MODE: str = os.getenv("KDB_MODE", "poc")         # "poc" | "server"
    KDB_DATA_PATH: str = os.getenv("KDB_DATA_PATH", "./data/kdb")   # poc mode
    KDB_HOST: str = os.getenv("KDB_HOST", "localhost")   # server mode
    KDB_PORT: int = int(os.getenv("KDB_PORT", "5000"))   # server mode

    # Observability (Langfuse + Phoenix + Dynatrace)
    OBSERVABILITY_ENABLED: bool = os.getenv("OBSERVABILITY_ENABLED", "false").lower() == "true"

    # Langfuse (graph view + metrics dashboard)
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

    # Phoenix / Arize (RAG + span analysis)
    PHOENIX_ENDPOINT: str = os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006")

    # Dynatrace (enterprise APM — OTel native, recommended for production)
    # Leave empty to disable (exporter is skipped when DYNATRACE_ENDPOINT is not set)
    DYNATRACE_ENDPOINT: str = os.getenv("DYNATRACE_ENDPOINT", "")   # https://{env}.live.dynatrace.com
    DYNATRACE_API_TOKEN: str = os.getenv("DYNATRACE_API_TOKEN", "")  # dt0c01....

    # A2A (Agent-to-Agent, Phase 2)
    # Set AWS_ENDPOINT_URL=http://localstack:4566 for local dev (empty = real AWS)
    DYNAMODB_ENDPOINT: str = os.getenv("AWS_ENDPOINT_URL", "")
    KDB_AGENT_URL: str = os.getenv("KDB_AGENT_URL", "http://localhost:8001")
    AMPS_AGENT_URL: str = os.getenv("AMPS_AGENT_URL", "http://localhost:8002")
    FINANCIAL_ORCHESTRATOR_URL: str = os.getenv("FINANCIAL_ORCHESTRATOR_URL", "http://localhost:8003")
    A2A_TIMEOUT: int = int(os.getenv("A2A_TIMEOUT", "120"))  # legacy fallback; prefer per-agent timeouts

    # A2A Phase 3 — new specialist agents
    PORTFOLIO_AGENT_URL: str = os.getenv("PORTFOLIO_AGENT_URL", "http://localhost:8004")
    CDS_AGENT_URL: str = os.getenv("CDS_AGENT_URL", "http://localhost:8005")
    ETF_AGENT_URL: str = os.getenv("ETF_AGENT_URL", "http://localhost:8006")
    RISK_PNL_AGENT_URL: str = os.getenv("RISK_PNL_AGENT_URL", "http://localhost:8007")

    # Phase 3 — new product enablement flags
    PORTFOLIO_ENABLED: bool = os.getenv("PORTFOLIO_ENABLED", "true").lower() == "true"
    CDS_ENABLED: bool = os.getenv("CDS_ENABLED", "true").lower() == "true"
    ETF_ENABLED: bool = os.getenv("ETF_ENABLED", "true").lower() == "true"

    # ── Phase 4: Guardrails ────────────────────────────────────────────────────
    # Max tool-use loop iterations inside a Strands agent (prevents infinite tool loops)
    AGENT_MAX_ITERATIONS: int = int(os.getenv("AGENT_MAX_ITERATIONS", "15"))
    # LangGraph cycle guard (recursion_limit passed to graph.compile)
    GRAPH_RECURSION_LIMIT: int = int(os.getenv("GRAPH_RECURSION_LIMIT", "25"))

    # Per-agent A2A timeouts (seconds) — tuned per data source latency profile
    AGENT_TIMEOUT_DEFAULT: int = int(os.getenv("AGENT_TIMEOUT_DEFAULT", "60"))
    AGENT_TIMEOUT_KDB: int = int(os.getenv("AGENT_TIMEOUT_KDB", "90"))       # KDB: large parquet scans
    AGENT_TIMEOUT_AMPS: int = int(os.getenv("AGENT_TIMEOUT_AMPS", "30"))     # AMPS: real-time, must be fast
    AGENT_TIMEOUT_FINANCIAL: int = int(os.getenv("AGENT_TIMEOUT_FINANCIAL", "90"))
    AGENT_TIMEOUT_PORTFOLIO: int = int(os.getenv("AGENT_TIMEOUT_PORTFOLIO", "60"))
    AGENT_TIMEOUT_CDS: int = int(os.getenv("AGENT_TIMEOUT_CDS", "60"))
    AGENT_TIMEOUT_ETF: int = int(os.getenv("AGENT_TIMEOUT_ETF", "60"))
    AGENT_TIMEOUT_RISK_PNL: int = int(os.getenv("AGENT_TIMEOUT_RISK_PNL", "90"))

    # Daily rate limiting per user (backed by DynamoDB token-usage table)
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    DAILY_REQUEST_LIMIT: int = int(os.getenv("DAILY_REQUEST_LIMIT", "1000"))
    TOKEN_USAGE_TABLE: str = os.getenv("TOKEN_USAGE_TABLE", "agentic-ai-staging-token-usage")

    # Debug
    LANGGRAPH_DEBUG: bool = os.getenv("LANGGRAPH_DEBUG", "false").lower() == "true"

    # Demo mode — pre-scripted responses for presentations (no API key needed)
    # Unmatched queries fall through to LLM_PROVIDER (ollama or mock as fallback)
    DEMO_MODE_ENABLED: bool = os.getenv("DEMO_MODE_ENABLED", "false").lower() == "true"

    @classmethod
    def is_local(cls) -> bool:
        return cls.LLM_PROVIDER in ("anthropic", "ollama", "mock")

    @classmethod
    def get_agent_url(cls, agent_id: str) -> str:
        """Fallback URL by agent_id when DynamoDB discovery fails."""
        _map = {
            "kdb-agent": cls.KDB_AGENT_URL,
            "amps-agent": cls.AMPS_AGENT_URL,
            "financial-orchestrator": cls.FINANCIAL_ORCHESTRATOR_URL,
            "portfolio-agent": cls.PORTFOLIO_AGENT_URL,
            "cds-agent": cls.CDS_AGENT_URL,
            "etf-agent": cls.ETF_AGENT_URL,
            "risk-pnl-agent": cls.RISK_PNL_AGENT_URL,
        }
        return _map.get(agent_id, f"http://{agent_id}:8000")

    @classmethod
    def get_agent_timeout(cls, agent_id: str) -> int:
        """Per-agent A2A timeout in seconds. Falls back to AGENT_TIMEOUT_DEFAULT."""
        _map = {
            "kdb-agent": cls.AGENT_TIMEOUT_KDB,
            "amps-agent": cls.AGENT_TIMEOUT_AMPS,
            "financial-orchestrator": cls.AGENT_TIMEOUT_FINANCIAL,
            "portfolio-agent": cls.AGENT_TIMEOUT_PORTFOLIO,
            "cds-agent": cls.AGENT_TIMEOUT_CDS,
            "etf-agent": cls.AGENT_TIMEOUT_ETF,
            "risk-pnl-agent": cls.AGENT_TIMEOUT_RISK_PNL,
        }
        return _map.get(agent_id, cls.AGENT_TIMEOUT_DEFAULT)

    @classmethod
    def validate(cls) -> None:
        if cls.LLM_PROVIDER == "anthropic" and not cls.ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic. "
                "Copy .env.example to .env and set your key. "
                "To run without a key use LLM_PROVIDER=mock (canned responses) "
                "or LLM_PROVIDER=bedrock (AWS IAM auth, no API key needed)."
            )


config = Config()
