"""
Dual observability setup: Langfuse + Phoenix (Arize)

Architecture
────────────
A single OpenTelemetry (OTEL) TracerProvider sends traces to BOTH backends
via two BatchSpanProcessors / OTLPSpanExporters:

    TracerProvider
    ├── BatchSpanProcessor → OTLPSpanExporter → Phoenix  :6006
    └── BatchSpanProcessor → OTLPSpanExporter → Langfuse :3000

LangChain / LangGraph instrumentation:
  • Phoenix  : LangChainInstrumentor (auto, openinference) → graph spans, RAG spans
  • Langfuse : CallbackHandler passed at graph.invoke()    → graph VIEW in UI

Strands Agents:
  • Emits OTEL spans natively (strands-agents[otel]).
    Those spans are captured by the TracerProvider automatically.

Usage
─────
Call `setup_observability()` once at process startup (done in main.py).
Call `get_langfuse_callback()` to get the handler for LangGraph.invoke().
"""
import base64
import logging

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

_initialized = False


def setup_observability() -> None:
    """
    Initialize the shared OTEL TracerProvider.

    - Adds a Phoenix exporter when PHOENIX_ENDPOINT is configured.
    - Adds a Langfuse exporter when LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY
      are configured.
    - Auto-instruments LangChain/LangGraph for Phoenix's span view.

    Safe to call multiple times (no-op after first call).
    """
    global _initialized
    if _initialized:
        return

    from src.config import config  # late import to avoid circular deps

    if not config.OBSERVABILITY_ENABLED:
        logger.debug("[observability] disabled – set OBSERVABILITY_ENABLED=true to enable.")
        return

    resource = Resource.create({"service.name": "agentic-ai-system"})
    provider = TracerProvider(resource=resource)
    exporters_added = 0

    # ── Phoenix exporter ──────────────────────────────────────────────────────
    if config.PHOENIX_ENDPOINT:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            phoenix_exporter = OTLPSpanExporter(
                endpoint=f"{config.PHOENIX_ENDPOINT}/v1/traces"
            )
            provider.add_span_processor(BatchSpanProcessor(phoenix_exporter))
            exporters_added += 1
            logger.info(f"[observability] Phoenix exporter → {config.PHOENIX_ENDPOINT}")
        except ImportError:
            logger.warning(
                "[observability] Phoenix exporter skipped – "
                "install opentelemetry-exporter-otlp-proto-http"
            )

    # ── Langfuse exporter ─────────────────────────────────────────────────────
    if config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            langfuse_auth = base64.b64encode(
                f"{config.LANGFUSE_PUBLIC_KEY}:{config.LANGFUSE_SECRET_KEY}".encode()
            ).decode()
            langfuse_exporter = OTLPSpanExporter(
                endpoint=f"{config.LANGFUSE_HOST}/api/public/otel/v1/traces",
                headers={"Authorization": f"Basic {langfuse_auth}"},
            )
            provider.add_span_processor(BatchSpanProcessor(langfuse_exporter))
            exporters_added += 1
            logger.info(f"[observability] Langfuse exporter → {config.LANGFUSE_HOST}")
        except ImportError:
            logger.warning(
                "[observability] Langfuse OTEL exporter skipped – "
                "install opentelemetry-exporter-otlp-proto-http"
            )

    if exporters_added == 0:
        logger.warning(
            "[observability] No exporters configured. "
            "Set PHOENIX_ENDPOINT and/or LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY."
        )
        return

    trace.set_tracer_provider(provider)

    # ── Phoenix: auto-instrument LangChain / LangGraph ────────────────────────
    # This captures every LangGraph node, LangChain call, and ChromaDB retrieval
    # as typed OpenInference spans (CHAIN, RETRIEVER, LLM, TOOL, AGENT…).
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor

        LangChainInstrumentor().instrument(tracer_provider=provider)
        logger.info("[observability] LangChain auto-instrumentation active (Phoenix).")
    except ImportError:
        logger.warning(
            "[observability] LangChain auto-instrumentation skipped – "
            "install openinference-instrumentation-langchain"
        )

    _initialized = True
    logger.info(
        f"[observability] Ready. {exporters_added} exporter(s) active. "
        "Phoenix UI: http://localhost:6006  Langfuse UI: http://localhost:3000"
    )


def get_langfuse_callback():
    """
    Return a Langfuse CallbackHandler for use in LangGraph graph.invoke().

    This enables the LangGraph **graph view** in the Langfuse UI:
    nodes light up as the graph executes, and you can inspect each
    node's input/output inline.

    Returns None if Langfuse is not configured or the package is missing.

    Usage:
        cb = get_langfuse_callback()
        config = {"callbacks": [cb]} if cb else {}
        graph.invoke(state, config=config)
    """
    from src.config import config  # late import

    if not (
        config.OBSERVABILITY_ENABLED
        and config.LANGFUSE_PUBLIC_KEY
        and config.LANGFUSE_SECRET_KEY
    ):
        return None

    try:
        from langfuse.langchain import CallbackHandler

        # Langfuse v3 reads LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST from env
        return CallbackHandler()
    except ImportError:
        logger.warning(
            "[observability] langfuse package not installed – "
            "run: pip install langfuse"
        )
        return None
