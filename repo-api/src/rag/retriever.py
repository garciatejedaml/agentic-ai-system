"""OpenSearch k-NN RAG retriever with local sentence-transformer embeddings."""
from __future__ import annotations

import hashlib
import logging
import warnings
from pathlib import Path
from typing import List

from src.config import config

logger = logging.getLogger(__name__)

# Suppress noisy HuggingFace / tokenizers warnings at import time
warnings.filterwarnings("ignore", category=FutureWarning)


class RAGRetriever:
    """
    Wraps an OpenSearch k-NN index with sentence-transformer embeddings.

    Local dev  → embeddings run on-device via sentence-transformers
    AWS prod   → swap SentenceTransformer for a Bedrock embedding call if needed

    Graceful fallback: if OpenSearch is unavailable at startup, the retriever
    logs a warning and operates in degraded mode (count=0, retrieve=[]).
    """

    _INDEX_MAPPING = {
        "settings": {
            "index.knn": True,
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        "mappings": {
            "properties": {
                "text":      {"type": "text"},
                "source":    {"type": "keyword"},
                "embedding": {
                    "type":      "knn_vector",
                    "dimension": 384,
                    "method": {
                        "name":        "hnsw",
                        "space_type":  "cosinesimil",
                        "engine":      "nmslib",
                        "parameters":  {"ef_construction": 128, "m": 16},
                    },
                },
            }
        },
    }

    def __init__(self) -> None:
        self._available = False
        self._client = None
        self._model = None

        # Connect to OpenSearch and load embedding model only if connection succeeds.
        # Skipping model load when OpenSearch is down saves ~400MB RAM.
        try:
            from opensearchpy import OpenSearch
            url = config.OPENSEARCH_URL  # e.g. "http://localhost:9200"
            # Strip scheme for host/port parsing
            host_part = url.replace("https://", "").replace("http://", "")
            host, _, port_str = host_part.partition(":")
            port = int(port_str) if port_str else 9200
            use_ssl = url.startswith("https://")

            self._client = OpenSearch(
                hosts=[{"host": host, "port": port}],
                use_ssl=use_ssl,
                verify_certs=False,
                ssl_show_warn=False,
                timeout=10,
                max_retries=2,
                retry_on_timeout=True,
            )
            self._index = config.OPENSEARCH_INDEX
            self._ensure_index()

            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(config.EMBEDDING_MODEL)
            self._available = True
            logger.info("[RAGRetriever] Connected to OpenSearch at %s, index=%s", url, self._index)
        except Exception as e:
            logger.warning(
                "[RAGRetriever] OpenSearch unavailable (%s). "
                "RAG will return empty context — system continues without RAG.",
                e,
            )

    # ── Index management ─────────────────────────────────────────────────────

    def _ensure_index(self) -> None:
        """Create the k-NN index if it does not exist."""
        if not self._client.indices.exists(index=self._index):
            self._client.indices.create(index=self._index, body=self._INDEX_MAPPING)
            logger.info("[RAGRetriever] Created index: %s", self._index)

    # ── Ingestion ────────────────────────────────────────────────────────────

    def add_texts(self, texts: List[str], metadatas: List[dict] | None = None) -> None:
        """Add a list of plain text chunks to the vector store (idempotent by content hash)."""
        if not self._available:
            logger.debug("[RAGRetriever] OpenSearch unavailable — skipping add_texts")
            return

        from opensearchpy import helpers

        metadatas = metadatas or [{} for _ in texts]
        embeddings = self._model.encode(texts, show_progress_bar=False).tolist()

        actions = []
        for text, meta, embedding in zip(texts, metadatas, embeddings):
            # Deterministic doc ID: sha256 of text — ensures idempotent re-ingest
            doc_id = hashlib.sha256(text.encode()).hexdigest()[:16]
            actions.append({
                "_op_type": "index",
                "_index":   self._index,
                "_id":      doc_id,
                "_source": {
                    "text":      text,
                    "source":    meta.get("source", ""),
                    "embedding": embedding,
                },
            })

        if actions:
            success, errors = helpers.bulk(self._client, actions, raise_on_error=False)
            if errors:
                logger.warning("[RAGRetriever] Bulk index errors: %s", errors[:3])

    def add_file(self, file_path: str | Path, chunk_size: int = 500) -> int:
        """Read a text file, split into chunks, and ingest into OpenSearch."""
        text = Path(file_path).read_text(encoding="utf-8")
        chunks = self._chunk_text(text, chunk_size)
        source = str(file_path)
        self.add_texts(chunks, metadatas=[{"source": source} for _ in chunks])
        return len(chunks)

    # ── Retrieval ────────────────────────────────────────────────────────────

    def retrieve(self, query: str, k: int | None = None) -> List[dict]:
        """
        Return the top-k most relevant chunks for `query` using k-NN similarity.

        Returns a list of dicts: {"text": ..., "source": ..., "distance": ...}
        Returns [] if OpenSearch is unavailable.
        """
        if not self._available:
            return []

        k = k or config.RAG_TOP_K
        query_vector = self._model.encode([query], show_progress_bar=False)[0].tolist()

        body = {
            "size": k,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": query_vector,
                        "k":      k,
                    }
                }
            },
            "_source": ["text", "source"],
        }

        try:
            response = self._client.search(index=self._index, body=body)
        except Exception as e:
            logger.warning("[RAGRetriever] Search failed: %s", e)
            return []

        docs = []
        for hit in response["hits"]["hits"]:
            src = hit["_source"]
            # OpenSearch k-NN returns score (higher = more similar), convert to distance
            docs.append({
                "text":     src.get("text", ""),
                "source":   src.get("source", ""),
                "distance": 1.0 - hit["_score"],  # cosinesimil score ∈ [0,1]
            })
        return docs

    def count(self) -> int:
        """Return total number of indexed chunks, or 0 if unavailable."""
        if not self._available:
            return 0
        try:
            return self._client.count(index=self._index)["count"]
        except Exception:
            return 0

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _chunk_text(text: str, chunk_size: int) -> List[str]:
        """Simple character-based chunking with 20% overlap."""
        overlap = chunk_size // 5
        chunks, start = [], 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end].strip())
            start = end - overlap
        return [c for c in chunks if c]

    @staticmethod
    def _chunk_markdown_sections(text: str, max_section_size: int = 1000) -> List[str]:
        """
        Split markdown by ## headers first (preserving coherent sections), then
        apply character chunking only on sections that exceed max_section_size.

        This avoids cutting tables or code blocks mid-row, which character-based
        chunking at small sizes causes. Sections up to ~1000 chars stay intact
        (250 tokens max — acceptable context for a focused schema question).
        """
        import re
        # Split on lines that start a ## section, keeping the header with its body
        raw_sections = re.split(r'\n(?=## )', text.strip())
        chunks = []
        for section in raw_sections:
            section = section.strip()
            if not section:
                continue
            if len(section) <= max_section_size:
                chunks.append(section)
            else:
                # Section too large (e.g. long field table) — character-split it
                chunks.extend(RAGRetriever._chunk_text(section, chunk_size=500))
        return [c for c in chunks if len(c) > 20]


# Singleton for reuse across nodes
_retriever: RAGRetriever | None = None


def get_retriever() -> RAGRetriever:
    global _retriever
    if _retriever is None:
        _retriever = RAGRetriever()
    return _retriever
