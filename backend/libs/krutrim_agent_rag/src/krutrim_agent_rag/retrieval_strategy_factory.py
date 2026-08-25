"""Pluggable `RetrievalStrategy` selection — same shape as
`vector_store_factory.py`. `retrieval_strategy.py`'s `VectorOnlyStrategy`
and `HybridStrategy` self-register `"vector_only"`/`"hybrid"` at import time.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from krutrim_agent_utils.plugin_registry import PluginRegistry

if TYPE_CHECKING:
    from krutrim_agent_rag.retrieval_strategy import RetrievalStrategy

_registry: PluginRegistry[Callable[[], RetrievalStrategy]] = PluginRegistry(
    kind="retrieval strategy"
)


def register_retrieval_strategy(
    key: str, factory: Callable[[], RetrievalStrategy]
) -> None:
    _registry.register(key, factory)


def create_retrieval_strategy() -> RetrievalStrategy:
    from krutrim_agent_management.config import settings

    _registry.discover_modules(settings.retrieval_strategy_sources)
    return _registry.get(settings.retrieval_strategy)()
