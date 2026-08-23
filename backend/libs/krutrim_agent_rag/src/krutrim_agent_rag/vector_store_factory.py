"""Pluggable `VectorStore` backend selection — same shape as
`krutrim_agent_management.storage_factory`. `embeddings.py`'s
`FaissliteVectorStore` self-registers `"faisslite"` at import time.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from krutrim_agent_utils.plugin_registry import PluginRegistry

if TYPE_CHECKING:
    from pathlib import Path

    from krutrim_agent_rag.embeddings import VectorStore

_registry: PluginRegistry[Callable[..., VectorStore]] = PluginRegistry(
    kind="vector store backend"
)


def register_vector_store_backend(
    key: str, factory: Callable[..., VectorStore]
) -> None:
    """`factory(embeddings_dir, *, dim=None, algorithm="flat") -> VectorStore` —
    same signature as `embeddings.open_index`, which is what calls through here."""
    _registry.register(key, factory)


def create_vector_store(
    embeddings_dir: Path, *, dim: int | None = None, algorithm: str = "flat"
) -> VectorStore:
    from krutrim_agent_management.config import settings

    _registry.discover_modules(settings.vector_store_backend_sources)
    return _registry.get(settings.vector_store_backend)(
        embeddings_dir, dim=dim, algorithm=algorithm
    )
