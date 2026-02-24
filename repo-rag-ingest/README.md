# repo-rag-ingest — RAG Ingestion Pipeline

Ingestion scripts and training data for the ChromaDB vector store.
Run these scripts once (or as a CI/CD step) to populate the RAG knowledge base
before starting the API.

## Structure

```
scripts/
  ingest_docs.py           ← Ingest sample docs into ChromaDB
  ingest_amps_docs.py      ← Ingest AMPS-specific documentation
  generate_synthetic_rfq.py ← Generate synthetic Bond RFQ Parquet data for KDB POC
data/
  sample_docs/             ← LangGraph + Strands intro texts
  kdb/                     ← bond_rfq.parquet (synthetic RFQ data)
amps/
  binaries/                ← AMPS server binaries (not in git — download from crankuptheamps.com)
  client/                  ← AMPS Python client zip (not in git — ships with binary)
```

## Run ingestion

```bash
# From the monorepo root (requires CHROMA_PERSIST_DIR set)
python repo-rag-ingest/scripts/ingest_docs.py
python repo-rag-ingest/scripts/ingest_amps_docs.py

# Regenerate synthetic KDB data
python repo-rag-ingest/scripts/generate_synthetic_rfq.py
```

In Docker, ingestion runs automatically on container startup via `entrypoint.sh`
(set `SKIP_INGEST=true` to skip).
