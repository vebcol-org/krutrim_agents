"""Text chunking shared by every RAG ingestion task (file-path and raw-text)."""

from __future__ import annotations

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100


def chunk_text(
    text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[str]:
    """Fixed-size character chunking with overlap — deliberately simple, no
    sentence/token awareness. A first pass at giving an agent recall over
    large documents, not a retrieval-quality optimization."""
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks
