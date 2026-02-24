"""ChromaDB-based RAG retriever with local sentence-transformer embeddings."""
from __future__ import annotations

import os
from pathlib import Path
from typing import List

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from src.config import config


class RAGRetriever:
    """
    Wraps a ChromaDB collection with sentence-transformer embeddings.

    Local dev  → embeddings run on-device via sentence-transformers
    AWS prod   → swap `embedding_fn` for BedrockEmbeddingFunction or similar
    """

    COLLECTION_NAME = "knowledge_base"

    def __init__(self) -> None:
        self._embedding_fn = SentenceTransformerEmbeddingFunction(
            model_name=config.EMBEDDING_MODEL
        )
        self._client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            embedding_function=self._embedding_fn,
        )

    # ── Ingestion ────────────────────────────────────────────────────────────

    def add_texts(self, texts: List[str], metadatas: List[dict] | None = None) -> None:
        """Add a list of plain text chunks to the vector store."""
        ids = [f"doc_{self._collection.count() + i}" for i in range(len(texts))]
        self._collection.add(
            documents=texts,
            metadatas=metadatas or [{} for _ in texts],
            ids=ids,
        )

    def add_file(self, file_path: str | Path, chunk_size: int = 500) -> int:
        """Read a text file, split into chunks, and ingest into ChromaDB."""
        text = Path(file_path).read_text(encoding="utf-8")
        chunks = self._chunk_text(text, chunk_size)
        source = str(file_path)
        self.add_texts(chunks, metadatas=[{"source": source} for _ in chunks])
        return len(chunks)

    # ── Retrieval ────────────────────────────────────────────────────────────

    def retrieve(self, query: str, k: int | None = None) -> List[dict]:
        """
        Return the top-k most relevant chunks for `query`.

        Returns a list of dicts: {"text": ..., "source": ..., "distance": ...}
        """
        k = k or config.RAG_TOP_K
        results = self._collection.query(
            query_texts=[query],
            n_results=min(k, self._collection.count() or 1),
        )
        docs = []
        for text, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            docs.append({"text": text, "source": meta.get("source", ""), "distance": dist})
        return docs

    def count(self) -> int:
        return self._collection.count()

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _chunk_text(text: str, chunk_size: int) -> List[str]:
        """Simple character-based chunking with overlap."""
        overlap = chunk_size // 5
        chunks, start = [], 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end].strip())
            start = end - overlap
        return [c for c in chunks if c]


# Singleton for reuse across nodes
_retriever: RAGRetriever | None = None


def get_retriever() -> RAGRetriever:
    global _retriever
    if _retriever is None:
        _retriever = RAGRetriever()
    return _retriever
