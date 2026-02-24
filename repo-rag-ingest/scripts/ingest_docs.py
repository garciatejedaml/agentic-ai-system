"""
Document ingestion script.

Usage:
    python scripts/ingest_docs.py                         # ingest data/sample_docs/
    python scripts/ingest_docs.py path/to/my/file.txt
    python scripts/ingest_docs.py path/to/docs/folder/
"""
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rag.retriever import RAGRetriever


def ingest(target: Path) -> None:
    retriever = RAGRetriever()

    files = []
    if target.is_dir():
        files = list(target.glob("**/*.txt")) + list(target.glob("**/*.md"))
    elif target.is_file():
        files = [target]
    else:
        print(f"Path not found: {target}")
        sys.exit(1)

    if not files:
        print(f"No .txt or .md files found in {target}")
        sys.exit(0)

    total = 0
    for f in files:
        n = retriever.add_file(f)
        print(f"  ✓ {f.name}  ({n} chunks)")
        total += n

    print(f"\nDone. {total} chunks across {len(files)} file(s) added to ChromaDB.")
    print(f"Total docs in collection: {retriever.count()}")


if __name__ == "__main__":
    path_arg = sys.argv[1] if len(sys.argv) > 1 else "data/sample_docs"
    ingest(Path(path_arg))
