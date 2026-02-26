#!/usr/bin/env python3
"""
AMPS Schema + Connection Ingestion Script

Two document tiers:

  Tier 1 — Connection cards (data/amps_connections/*.md)
    One file per AMPS instance (~250 chars each). Ingested as a single chunk.
    The agent searches these to discover host:port before calling amps_sow_query.

  Tier 2 — Schema docs (data/amps_schemas/*.md)
    Full field reference per topic. Chunked by ## section (not by character),
    so tables and code blocks are never split mid-row.

Usage:
  python scripts/ingest_amps_schemas.py             # ingest both tiers
  python scripts/ingest_amps_schemas.py --dry-run   # list docs without ingesting
"""
import argparse
import os
import sys
from pathlib import Path

# Allow running from repo root (local) or /app (Docker)
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rag.retriever import get_retriever

_CONNECTIONS_DIR = Path(__file__).parent.parent / "data" / "amps_connections"
_SCHEMAS_DIR     = Path(__file__).parent.parent / "data" / "amps_schemas"

_CONNECTION_FILES = [
    "amps_core_connection.md",
    "amps_portfolio_connection.md",
    "amps_cds_connection.md",
    "amps_etf_connection.md",
    "amps_risk_connection.md",
]

_SCHEMA_FILES = [
    "positions_topic.md",
    "orders_topic.md",
    "market_data_topic.md",
    "portfolio_nav_topic.md",
    "cds_spreads_topic.md",
    "etf_nav_topic.md",
    "risk_metrics_topic.md",
]


def _read_dir(directory: Path, filenames: list[str]) -> list[dict]:
    docs = []
    for fname in filenames:
        path = directory / fname
        if not path.exists():
            print(f"  [warn] Not found, skipping: {path}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
            if len(text.strip()) < 20:
                print(f"  [warn] Too short, skipping: {fname}")
                continue
            docs.append({"source": fname, "text": text})
        except Exception as e:
            print(f"  [warn] Could not read {fname}: {e}")
    return docs


def ingest(dry_run: bool = False) -> None:
    connection_docs = _read_dir(_CONNECTIONS_DIR, _CONNECTION_FILES)
    schema_docs     = _read_dir(_SCHEMAS_DIR, _SCHEMA_FILES)

    print(f"\n[ingest] Tier 1 — Connection cards ({len(connection_docs)} files, single-chunk each):")
    for doc in connection_docs:
        print(f"  {doc['source']:<35} ({len(doc['text']):>4} chars = 1 chunk)")

    print(f"\n[ingest] Tier 2 — Schema docs ({len(schema_docs)} files, section-chunked):")
    retriever_tmp = get_retriever() if not dry_run else None
    for doc in schema_docs:
        # Preview chunk count without loading model
        import re
        sections = [s.strip() for s in re.split(r'\n(?=## )', doc['text'].strip()) if s.strip()]
        print(f"  {doc['source']:<35} ({len(doc['text']):>5} chars → {len(sections)} sections)")

    if dry_run:
        print("\n[ingest] Dry run — skipping actual ingest.")
        return

    retriever = get_retriever()

    # ── Tier 1: connection cards — one chunk each ────────────────────────────
    print("\n[ingest] Ingesting connection cards (1 chunk each)...")
    conn_chunks = 0
    for doc in connection_docs:
        retriever.add_texts(
            texts=[doc["text"].strip()],
            metadatas=[{"source": doc["source"]}],
        )
        conn_chunks += 1
        print(f"  ✓ {doc['source']}")

    # ── Tier 2: schema docs — section-based chunking ─────────────────────────
    print("\n[ingest] Ingesting schema docs (section chunking, max 1000 chars/section)...")
    schema_chunks = 0
    for doc in schema_docs:
        chunks = retriever._chunk_markdown_sections(doc["text"], max_section_size=1000)
        retriever.add_texts(
            texts=chunks,
            metadatas=[{"source": doc["source"]} for _ in chunks],
        )
        schema_chunks += len(chunks)
        print(f"  ✓ {doc['source']:<35} → {len(chunks)} chunks")

    total = retriever.count()
    print(f"\n[ingest] Done.")
    print(f"  Connection cards: {conn_chunks} chunks")
    print(f"  Schema sections:  {schema_chunks} chunks")
    print(f"  RAG total:        {total} chunks")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest AMPS connection cards + schema docs into the RAG knowledge base"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.getenv("DRY_RUN", "false").lower() == "true",
        help="List docs and chunk counts without ingesting",
    )
    args = parser.parse_args()
    ingest(dry_run=args.dry_run)
