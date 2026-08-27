# `krutrim_agent_rag` (backend/libs/krutrim_agent_rag)

Package name: **`krutrim-agent-rag`** (`backend/libs/krutrim_agent_rag/pyproject.toml`). RAG library: session-scoped vector-store I/O (FAISS or Qdrant), chunking, OpenRouter embeddings, a pluggable retrieval strategy (vector-only or hybrid vector+BM25), the agent-initiated `rag_tool`, and a `RagInjectionMiddleware` wired into the `research` profile behind a feature flag. Depends on `krutrim_agent_management` (for `Storage`/`settings`) and `krutrim_agent_utils` (the `PluginRegistry`).

```
krutrim_agent_rag/
├── models.py                       StoredChunk, RetrievedChunk — backend-agnostic result types
├── embeddings.py                   VectorStore ABC + FaissliteVectorStore; self-registers "faisslite"
├── qdrant_store.py                 QdrantVectorStore; self-registers "qdrant"
├── vector_store_factory.py         create_vector_store(...) — same shape as krutrim_agent_management.storage_factory
├── chunking.py                     chunk_text(...) — shared by both RAG ingestion tasks
├── embeddings_provider.py          default_embed(...) — OpenRouter embeddings
├── retrieval.py                    retrieve(...) — resolves the session's index, dispatches to a strategy
├── retrieval_strategy.py           VectorOnlyStrategy, HybridStrategy (vector + BM25 via RRF)
├── retrieval_strategy_factory.py   create_retrieval_strategy(...) — same shape as vector_store_factory
├── tool.py                         rag_tool — agent-initiated retrieval tool
└── middleware.py                   RagInjectionMiddleware — opt-in silent injection
```

## `embeddings.py` + `qdrant_store.py` + `vector_store_factory.py`

Session-scoped embedding-index **I/O only** — no embedding computation or chunking happens here (that's `chunking.py`/`embeddings_provider.py` and the `krutrim_agent_celery` ingestion tasks that call them).

- `VectorStore(ABC)` — the base vectordb interface every backend implements: `add(vectors, *, source, texts)`, `save()`, `search(query, k=5, *, source=None) -> list[StoredChunk]`, `get(id) -> StoredChunk | None`, `delete(*, source)`, `scroll(*, batch_size=256) -> Iterator[StoredChunk]`. Returns `StoredChunk` (defined in `models.py`) — never a backend-specific type — so callers work unchanged regardless of which backend is active. `delete`/`scroll` exist for idempotent re-ingest (delete-then-add on re-upload) and `retrieval_strategy.HybridStrategy`'s BM25 corpus, respectively.
- `FaissliteVectorStore(VectorStore)` — wraps a `faisslite.Store`, implementing `delete`/`scroll` on top of faisslite's native `Store.delete(ids)` (soft-delete/tombstone) and `store.meta.live_ids(source=...)`/`get_many(...)` (no native delete-by-source or scroll primitive, but both compose from what's there). Still also exposes faisslite's full API via `__getattr__` delegation for anything beyond the formal ABC methods.
- `QdrantVectorStore(VectorStore)` (`qdrant_store.py`) — wraps `qdrant_client.QdrantClient`. One Qdrant collection per session, named `session_{session_id}` (embeddings_dir's *parent* directory name — `embeddings_dir.name` is always literally `"embeddings"`, so the session id has to come from one level up). Deterministic point ids (`uuid5(source:chunk_index)`) make `add` after `delete(source=...)` idempotent, same guarantee as faisslite. Opt-in via `settings.vector_store_backend = "qdrant"`; `settings.qdrant_url`/`qdrant_api_key` configure the client.
- `open_index(embeddings_dir, *, dim=None, algorithm="flat") -> VectorStore` — resolves through `vector_store_factory.create_vector_store(...)`, so it returns whichever backend `settings.vector_store_backend` selects, `"faisslite"` by default. `dim` required only the first time (no index on disk yet).
- `index_exists(embeddings_dir) -> bool` — checks for `index.faiss` (faisslite-specific; doesn't reflect a Qdrant-backed session).
- `vector_store_factory.create_vector_store(embeddings_dir, *, dim=None, algorithm="flat") -> VectorStore` — resolves `settings.vector_store_backend` against a `krutrim_agent_utils.PluginRegistry`, discovered from `settings.vector_store_backend_sources` (default includes both `krutrim_agent_rag.embeddings` and `krutrim_agent_rag.qdrant_store`, so either key resolves regardless of which is active). Same shape as `krutrim_agent_management.storage_factory`.

## `retrieval_strategy.py` + `retrieval_strategy_factory.py`

A second, independent axis from the vector-store backend above: `vector_store_factory` decides *which database* stores vectors; this decides *how retrieval works* against whichever store is active.

- `RetrievalStrategy(ABC)` — one method, `retrieve(store, query, *, k, embed_fn) -> list[RetrievedChunk]`.
- `VectorOnlyStrategy` — today's original behavior: embed the query, `store.search(...)`.
- `HybridStrategy` — vector search plus BM25 (`rank_bm25.BM25Okapi`) over `store.scroll()`'s full corpus, fused by reciprocal rank fusion (no score-normalization tuning needed, unlike a weighted-alpha blend of two differently-scaled scores).
- Selected via `settings.retrieval_strategy` (`"vector_only"` default, or `"hybrid"`), resolved the same self-registering-`PluginRegistry` way as `vector_store_factory`. `retrieval.py::retrieve()` is the only caller — `tool.py`/`middleware.py` need no changes when the strategy changes.

## `chunking.py`

`chunk_text(text, chunk_size=1000, overlap=100) -> list[str]` — fixed-size character chunking with overlap, deliberately simple (no sentence/token awareness): a first pass at giving an agent recall over large documents, not a retrieval-quality optimization. Raises `ValueError` if `overlap >= chunk_size`; returns `[]` for empty text; returns the whole text as a single chunk if it's already under `chunk_size`.

Moved here from `krutrim_agent_celery`'s `precompute_embeddings.py` so both RAG ingestion tasks (`precompute_embeddings` and `process_rag_document`, see [`services/krutrim_agent_celery.md`](../services/krutrim_agent_celery.md)) share one implementation. `precompute_embeddings.py` re-exports `chunk_text`/`CHUNK_SIZE`/`CHUNK_OVERLAP` for backward-compat import.

## `embeddings_provider.py`

`default_embed(texts: list[str]) -> np.ndarray` — the default embedder for every RAG ingestion path (both `/embed` and `/rag/text`). Calls OpenRouter's OpenAI-compatible embeddings endpoint via `langchain_openai.OpenAIEmbeddings`, `base_url="https://openrouter.ai/api/v1"`, model from `settings.rag_embedding_model` (default `"qwen/qwen3-embedding-8b"`). Requires `OPENROUTER_API_KEY` in the environment. The `langchain_openai` import is deferred inside the function so `krutrim_agent_celery` workers that never run a RAG ingestion task don't pay for it at import time.

**Why OpenRouter, not local Ollama:** a session's FAISS index must never mix vectors from two different embedding models — distances (cosine/L2) stop meaning anything once vectors from two models share an index. `precompute_embeddings.py`'s `/embed` path was switched from `langchain_ollama.OllamaEmbeddings` to this same `default_embed` for exactly that reason, so every ingestion path into a given session's index uses one consistent embedder regardless of which route wrote to it (see [`services/krutrim_agent_celery.md`](../services/krutrim_agent_celery.md)). This lives here, not in `krutrim_agents_core/providers/`, because `krutrim_agent_celery` must never depend on `krutrim_agents`/`krutrim_agents_core` — workers shouldn't have to pull in the full LLM/agent stack just to embed text.

## `retrieval.py`

`retrieve(store, session_id, query, *, k=5, embed_fn=default_embed) -> list[RetrievedChunk]` — the shared top-k retrieval core behind both `tool.rag_tool` and `middleware.RagInjectionMiddleware`. Resolves the session's index and dispatches to whichever `RetrievalStrategy` is configured (above); no signature change for these two callers regardless of which strategy runs. `RetrievedChunk` is a frozen dataclass (`models.py`): `text`, `source`, `score`.

Returns `[]` gracefully — not an error — if the session has no index yet (a research run early in its lifecycle, before anything's been ingested, is a normal state).

## `tool.py` — `rag_tool`

The agent-initiated retrieval tool the `research` profile's prompts describe explicitly ("The user will supply domain-specific or private context via a `rag_tool` ... you must query for it"). Tool-call semantics, not silent injection: the agent decides when to call it, and tags results `[RAG]` in its own source log per `research-agent-rag-prompt.md`.

Reads `session_id` from the LangGraph run's `thread_id` via `langgraph.config.get_config()` **at call time**, rather than being pre-bound via a factory closure. This keeps `rag_tool` a normal static tool registered once in a profile's `_tools()`, with no need to widen `AgentProfile.tools_factory`'s no-argument signature to thread a `session_id` through. `thread_id` is set to the session id for every real run (`agent_run.py` passes the frontend's `threadId`, which the frontend sets to `sessionId`) — the same value the run's own checkpointer is keyed by.

Returns `"No matching context found."` (not an error) if nothing relevant has been ingested yet, and `"Error: no active session — rag_tool needs a running agent session."` if called outside a running session. The actual `retrieve` call (sync I/O — faisslite plus the embedding HTTP call) is offloaded via `asyncio.to_thread`, matching this codebase's general async-tool convention (`web_search` does the same for its sync DDGS call).

## `middleware.py` — `RagInjectionMiddleware`

Silent retrieval injection: on every model call, retrieves top-k context for the latest `HumanMessage` and prepends it (wrapped in `<retrieved_context>` tags) to the system message via `wrap_model_call`, with no tool call visible in the trace. Shares its retrieval core with `tool.rag_tool` (`retrieval.retrieve`) so both mechanisms stay consistent — and stay independent: this is additive to `rag_tool`, not a replacement for it.

**Wired into the `research` profile, off by default**, gated by `settings.rag_injection_enabled` (`KRUTRIM_AGENT_RAG_INJECTION_ENABLED=true` to enable). See `krutrim_agents/profiles/research/__init__.py`'s `_graph_pattern` — it appends `RagInjectionMiddleware()` to `context.middleware` only when the flag is set, scoped to `research` alone (`build_agent()`'s own profile-agnostic middleware list is untouched). Default `False` preserves `research`'s original behavior (tool-call semantics only) until an operator opts in.

## Dependencies

[`pyproject.toml`](../../libs/krutrim_agent_rag/pyproject.toml) — package `krutrim-agent-rag`: `faisslite` (git dependency — FAISS embedding-index I/O), `qdrant-client` (Qdrant backend), `rank-bm25` (hybrid retrieval), `numpy`, `langchain-core`, `langchain-openai`, plus the internal workspace deps `krutrim-agent-management` and `krutrim-agent-utils`. **No** dependency on `krutrim-agents`/`krutrim-agents-core`/`krutrim-agent-backend` — this package stays usable from `krutrim_agent_celery` workers, which must not pull in the full LLM/agent stack. (Document parsing beyond plain text — PDF/DOCX — lives in the separate [`krutrim_agent_doc`](krutrim_agent_doc.md) package, a dependency of `krutrim_agent_celery` only, to keep this package's own dependency footprint light.)

## Relevant tests

- `backend/tests/test_embeddings.py` — pure I/O against a real (fast, local, no network) faisslite `Store`, including `delete`/`scroll`.
- `backend/tests/test_qdrant_vector_store.py` — same shape, against Qdrant's in-process `:memory:` mode (no real server needed).
- `backend/tests/test_vector_store_factory.py` — backend registration/resolution.
- `backend/tests/test_retrieval_strategy.py` — strategy registration/resolution, plus a correctness check that `HybridStrategy` surfaces a keyword match pure vector search misses.
- `backend/tests/test_research_rag_injection.py` — `research`'s `_graph_pattern` includes/excludes `RagInjectionMiddleware` per `settings.rag_injection_enabled`.
