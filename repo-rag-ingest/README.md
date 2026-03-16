# repo-rag-ingest — RAG Ingestion Pipeline

Scripts and source data for populating the knowledge base used by the Agentic AI System's RAG layer. The knowledge base stores agent capability descriptions, AMPS topic schemas, and connection documentation so the LLM Router can make better routing decisions.

Run these scripts **once** before starting the API for the first time, or as a CI/CD step when schemas change.

---

## What gets ingested

| Script | Source data | Target index |
|--------|------------|--------------|
| `ingest_docs.py` | `data/sample_docs/` — LangGraph + Strands overviews | `knowledge_base` |
| `ingest_amps_docs.py` | `data/amps_connections/` — AMPS host/port/auth docs | `knowledge_base` |
| `ingest_amps_schemas.py` | `data/amps_schemas/` — topic field definitions | `knowledge_base` |
| `generate_synthetic_rfq.py` | Generates `data/kdb/bond_rfq.parquet` | File only (no index) |

The embedding model is `all-MiniLM-L6-v2` (384 dimensions, runs inside the container — no external API needed).

---

## Local ingestion (Docker)

Ingestion runs automatically on container startup via `entrypoint.sh`. Skip it on subsequent starts to save boot time:

```bash
# First start — ingestion runs automatically
docker compose --profile agents up -d

# Subsequent starts — skip ingestion
SKIP_INGEST=true docker compose --profile agents up -d
# or set SKIP_INGEST=true in .env
```

---

## Manual ingestion (local Python)

Requires OpenSearch running locally (`docker compose --profile rag up -d`):

```bash
cd repo-rag-ingest

pip install opensearch-py sentence-transformers python-dotenv

# Set OpenSearch URL
export OPENSEARCH_URL=http://localhost:9200

python scripts/ingest_docs.py
python scripts/ingest_amps_docs.py
python scripts/ingest_amps_schemas.py

# Regenerate synthetic KDB bond RFQ data (run once, output checked into git)
python scripts/generate_synthetic_rfq.py
```

---

## AWS ingestion (OpenSearch Service)

When deploying to AWS, point the scripts at your OpenSearch Service domain:

```bash
export OPENSEARCH_URL=https://search-your-domain.us-east-1.es.amazonaws.com
export AWS_DEFAULT_REGION=us-east-1

# If the domain uses fine-grained access control, set credentials:
export OPENSEARCH_USERNAME=admin
export OPENSEARCH_PASSWORD=your-password

python scripts/ingest_docs.py
python scripts/ingest_amps_docs.py
python scripts/ingest_amps_schemas.py
```

The Terraform in `repo-infra/` provisions an OpenSearch Service domain and passes the endpoint to the ECS task via environment variable. Run ingestion once after `terraform apply` before the first query.

---

## Source data

```
data/
  sample_docs/
    langraph_intro.txt      LangGraph concepts and StateGraph patterns
    strands_intro.txt       Strands Agents tool use and event loop
  amps_connections/
    amps_core_connection.md     Host, port, auth for AMPS Core instance
    amps_portfolio_connection.md
    amps_cds_connection.md
    amps_etf_connection.md
    amps_risk_connection.md
  amps_schemas/
    positions_topic.md      Field names and types for the positions SOW topic
    orders_topic.md
    market_data_topic.md
    portfolio_nav_topic.md
    cds_spreads_topic.md
    etf_nav_topic.md
    risk_metrics_topic.md
  kdb/
    bond_rfq.parquet        Synthetic 6-month HY bond RFQ history (generated)
```

To add new knowledge (e.g. a new AMPS topic or agent capability), drop a Markdown file in the appropriate `data/` subdirectory and re-run the relevant ingestion script.
