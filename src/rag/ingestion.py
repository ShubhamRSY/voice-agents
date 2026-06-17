"""Document ingestion pipeline for knowledge base."""

import re
from pathlib import Path

import structlog

from src.rag.vector_store import VectorStore

logger = structlog.get_logger()


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start = end - overlap
    return chunks


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def ingest_file(
    file_path: str | Path,
    vector_store: VectorStore | None = None,
    metadata: dict | None = None,
) -> int:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    text = clean_text(path.read_text(encoding="utf-8"))
    chunks = chunk_text(text)
    store = vector_store or VectorStore()

    metadatas = [
        {**(metadata or {}), "source": str(path), "chunk_index": i}
        for i in range(len(chunks))
    ]
    count = store.add_documents(chunks, metadatas)
    logger.info("ingested_documents", file=str(path), chunks=count)
    return count


def ingest_directory(
    directory: str | Path,
    vector_store: VectorStore | None = None,
) -> int:
    path = Path(directory)
    total = 0
    for file_path in path.glob("**/*"):
        if file_path.suffix in {".txt", ".md", ".json"}:
            total += ingest_file(file_path, vector_store)
    return total
