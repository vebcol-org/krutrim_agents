"""OpenRouter-hosted embeddings — the default embedder for every RAG ingestion
path (file-path `/embed` and raw-text `/rag/text`), replacing the previous
local-Ollama-only default so a session's FAISS index never mixes vectors from
two different embedding models (mixing spaces silently corrupts retrieval —
cosine/L2 distances stop meaning anything across models).

Lives here, not `krutrim_agents_core/providers/`, because `krutrim_agent_celery`
must never depend on `krutrim_agents`/`krutrim_agents_core` (workers don't pull
in the full LLM/agent stack) — see that service's `pyproject.toml`.
"""

from __future__ import annotations

import os

import numpy as np


def default_embed(texts: list[str]) -> np.ndarray:
    """OpenRouter's OpenAI-compatible embeddings endpoint. Requires
    `OPENROUTER_API_KEY`. Import is deferred so `krutrim_agent_celery` doesn't
    pay for `langchain_openai` at import time for workers that never run a
    RAG ingestion task — same convention as the embedder this replaced."""
    from krutrim_agent_management.config import settings
    from langchain_openai import OpenAIEmbeddings

    embeddings = OpenAIEmbeddings(
        model=settings.rag_embedding_model,
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url=os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1",
    )
    vectors = embeddings.embed_documents(texts)
    return np.asarray(vectors, dtype="float32")
