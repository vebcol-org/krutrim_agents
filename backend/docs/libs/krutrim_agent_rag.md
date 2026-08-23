# `krutrim_agent_rag` (backend/libs/krutrim_agent_rag)

Package name: **`krutrim-agent-rag`** (`backend/libs/krutrim_agent_rag/pyproject.toml`). RAG library: session-scoped FAISS vector-store I/O, chunking, OpenRouter embeddings, retrieval, the agent-initiated `rag_tool`, and an opt-in retrieval-injection middleware. Relocated out of [`krutrim_agent_management`](krutrim_agent_management.md) — a clean cutover (no shim left behind) — so RAG concerns own their own package rather than living inside the storage foundation library. Depends on `krutrim_agent_management` (for `Storage`/`settings`) and `krutrim_agent_utils` (the `PluginRegistry`).

```
krutrim_agent_rag/
├── embeddings.py               VectorStore ABC + FaissliteVectorStore; self-registers "faisslite"
├── vector_store_factory.py       create_vector_store(...) — same shape as krutrim_agent_management.storage_factory
├── chunking.py                     chunk_text(...) — shared by both RAG ingestion tasks
├── embeddings_provider.py            default_embed(...) — OpenRouter embeddings
├── retrieval.py                        retrieve(...) — shared top-k retrieval core
├── tool.py                               rag_tool — agent-initiated retrieval tool
└── middleware.py                           RagInjectionMiddleware — opt-in silent injection
```

## `embeddings.py` + `vector_store_factory.py`

Session-scoped embedding-index **I/O only** — no embedding computation or chunking happens here (that's `chunking.py`/`embeddings_provider.py` and the `krutrim_agent_celery` ingestion tasks that call them).

- `VectorStore(ABC)` — `add(vectors, *, source, texts)`, `save()`, and now `search(query, k=5, *, source=None) -> list[SearchResult]`. `search` is a **formal** abstract method here — unlike the pre-move version in `krutrim_agent_management`, which had no `search`/`query` on the ABC because nothing in the live request path called one yet; retrieval (`retrieval.py`, below) is that live caller now.
- `FaissliteVectorStore(VectorStore)` — wraps a `faisslite.Store`. Still also exposes faisslite's full API (`count`/`get`/...) via `__getattr__` delegation for anything beyond the three formal methods — exercised directly by its own tests (`tests/test_embeddings.py`).
- `open_index(embeddings_dir, *, dim=None, algorithm="flat") -> VectorStore` — resolves through `vector_store_factory.create_vector_store(...)`, so it returns whichever backend `settings.vector_store_backend` selects, `"faisslite"` by default. `dim` required only the first time (no index on disk yet).
- `index_exists(embeddings_dir) -> bool` — checks for `index.faiss` (faisslite-specific today).
- `vector_store_factory.create_vector_store(embeddings_dir, *, dim=None, algorithm="flat") -> VectorStore` — resolves `settings.vector_store_backend` against a `krutrim_agent_utils.PluginRegistry`, discovered from `settings.vector_store_backend_sources` (default `["krutrim_agent_rag.embeddings"]`, whose import self-registers `"faisslite"`). Same shape as `krutrim_agent_management.storage_factory`.

## `chunking.py`

`chunk_text(text, chunk_size=1000, overlap=100) -> list[str]` — fixed-size character chunking with overlap, deliberately simple (no sentence/token awareness): a first pass at giving an agent recall over large documents, not a retrieval-quality optimization. Raises `ValueError` if `overlap >= chunk_size`; returns `[]` for empty text; returns the whole text as a single chunk if it's already under `chunk_size`.

Moved here from `krutrim_agent_celery`'s `precompute_embeddings.py` so both RAG ingestion tasks (`precompute_embeddings` and `process_rag_document`, see [`services/krutrim_agent_celery.md`](../services/krutrim_agent_celery.md)) share one implementation. `precompute_embeddings.py` re-exports `chunk_text`/`CHUNK_SIZE`/`CHUNK_OVERLAP` for backward-compat import.

## `embeddings_provider.py`

`default_embed(texts: list[str]) -> np.ndarray` — the default embedder for every RAG ingestion path (both `/embed` and `/rag/text`). Calls OpenRouter's OpenAI-compatible embeddings endpoint via `langchain_openai.OpenAIEmbeddings`, `base_url="https://openrouter.ai/api/v1"`, model from `settings.rag_embedding_model` (default `"qwen/qwen3-embedding-8b"`). Requires `OPENROUTER_API_KEY` in the environment. The `langchain_openai` import is deferred inside the function so `krutrim_agent_celery` workers that never run a RAG ingestion task don't pay for it at import time.

**Why OpenRouter, not local Ollama:** a session's FAISS index must never mix vectors from two different embedding models — distances (cosine/L2) stop meaning anything once vectors from two models share an index. `precompute_embeddings.py`'s `/embed` path was switched from `langchain_ollama.OllamaEmbeddings` to this same `default_embed` for exactly that reason, so every ingestion path into a given session's index uses one consistent embedder regardless of which route wrote to it (see [`services/krutrim_agent_celery.md`](../services/krutrim_agent_celery.md)). This lives here, not in `krutrim_agents_core/providers/`, because `krutrim_agent_celery` must never depend on `krutrim_agents`/`krutrim_agents_core` — workers shouldn't have to pull in the full LLM/agent stack just to embed text.

## `retrieval.py`

`retrieve(store, session_id, query, *, k=5, embed_fn=default_embed) -> list[RetrievedChunk]` — the shared top-k retrieval core behind both `tool.rag_tool` and `middleware.RagInjectionMiddleware`. `RetrievedChunk` is a frozen dataclass: `text`, `source`, `score`.

Returns `[]` gracefully — not an error — if the session has no index yet, or the index exists but has no live vectors (a research run early in its lifecycle, before anything's been ingested, is a normal state). Catches `faisslite.exceptions.FaissliteError` around the actual `search` call for the same reason.

## `tool.py` — `rag_tool`

The agent-initiated retrieval tool the `research` profile's prompts describe explicitly ("The user will supply domain-specific or private context via a `rag_tool` ... you must query for it"). Tool-call semantics, not silent injection: the agent decides when to call it, and tags results `[RAG]` in its own source log per `research-agent-rag-prompt.md`.

Reads `session_id` from the LangGraph run's `thread_id` via `langgraph.config.get_config()` **at call time**, rather than being pre-bound via a factory closure. This keeps `rag_tool` a normal static tool registered once in a profile's `_tools()`, with no need to widen `AgentProfile.tools_factory`'s no-argument signature to thread a `session_id` through. `thread_id` is set to the session id for every real run (`agent_run.py` passes the frontend's `threadId`, which the frontend sets to `sessionId`) — the same value the run's own checkpointer is keyed by.

Returns `"No matching context found."` (not an error) if nothing relevant has been ingested yet, and `"Error: no active session — rag_tool needs a running agent session."` if called outside a running session. The actual `retrieve` call (sync I/O — faisslite plus the embedding HTTP call) is offloaded via `asyncio.to_thread`, matching this codebase's general async-tool convention (`web_search` does the same for its sync DDGS call).

## `middleware.py` — `RagInjectionMiddleware`

Opt-in, silent retrieval injection — the literal "middleware inject into our agent" shape: on every model call, retrieves top-k context for the latest `HumanMessage` and prepends it (wrapped in `<retrieved_context>` tags) to the system message via `wrap_model_call`, with no tool call visible in the trace. Shares its retrieval core with `tool.rag_tool` (`retrieval.retrieve`) so both mechanisms stay consistent.

**Off by default for the `research` profile** — its own prompts describe `rag_tool` as agent-initiated and tagged `[RAG]` in its own source log, i.e. tool-call semantics, not silent injection. This reconciles the "tool vs middleware" tension from the original feature ask: both were built, but only `rag_tool` is wired into `research` today. `RagInjectionMiddleware` is available for other profiles, or a future `research` "always augment" mode, that want context injected without the model having to ask for it.

## Dependencies

[`pyproject.toml`](../../libs/krutrim_agent_rag/pyproject.toml) — package `krutrim-agent-rag`: `faisslite` (git dependency — embedding-index I/O), `numpy`, `langchain-core`, `langchain-openai`, plus the internal workspace deps `krutrim-agent-management` and `krutrim-agent-utils`. **No** dependency on `krutrim-agents`/`krutrim-agents-core`/`krutrim-agent-backend` — this package stays usable from `krutrim_agent_celery` workers, which must not pull in the full LLM/agent stack.

## Relevant tests

- `backend/tests/test_embeddings.py` — moved/renamed import path from `krutrim_agent_management.embeddings` to `krutrim_agent_rag.embeddings`; pure I/O against a real (fast, local, no network) faisslite `Store`.
- `backend/tests/test_vector_store_factory.py` — new file, split out of the old `test_storage_factory.py`, which used to mix `Storage`-backend tests and `VectorStore`-backend tests in one file. `test_storage_factory.py` now covers only `Storage` backend selection.
