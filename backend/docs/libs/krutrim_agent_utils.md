# `krutrim_agent_utils` (backend/libs/krutrim_agent_utils)

Package name: **`krutrim-agent-utils`** (`backend/libs/krutrim_agent_utils/pyproject.toml`). Zero internal workspace dependencies — the foundation every other package (including `krutrim_agent_management`) sits on. Two small, generic pieces extracted because they were about to be (or already had been) duplicated across the workspace, not speculative infrastructure:

```
krutrim_agent_utils/
├── plugin_registry.py   PluginRegistry[T] — keyed registry + dotted-module-path discovery
└── atomic_write.py        atomic_write_bytes() / atomic_write_json()
```

## 1. `plugin_registry.py` — `PluginRegistry[T]`

[`plugin_registry.py`](../../libs/krutrim_agent_utils/src/krutrim_agent_utils/plugin_registry.py) — the one implementation, in the whole workspace, of "scan a list of dotted module paths, import each, let import-time side effects register things into a shared dict." Before this existed, `krutrim_agents_core.registry` had its own copy of this loop; it was about to be re-implemented three more times (storage backends, sandbox runtimes, security-extension hooks) before being extracted here instead.

```python
class PluginRegistry(Generic[T]):
    def __init__(self, *, kind: str) -> None: ...
    def register(self, key: str, value: T, *, replace: bool = False) -> None: ...
    def get(self, key: str) -> T: ...
    def all(self) -> dict[str, T]: ...
    def discard(self, key: str) -> None: ...
    def discover_packages(self, sources: Sequence[str]) -> None: ...
    def discover_modules(self, sources: Sequence[str]) -> None: ...
```

- **`kind`** — a human-readable noun (`"agent profile"`, `"sandbox runtime"`, `"extension hook"`) used only to make `register`/`get` error messages self-explanatory.
- **`register(key, value, *, replace=False)`** — raises `ValueError` on a duplicate key unless `replace=True`. Two distinct usage shapes share this one method:
  - **Additive, one-key-per-registration** (agent profiles, storage backends, sandbox runtimes) — every key is expected to be registered exactly once; a duplicate is a real bug (two profiles with the same key), so the default `replace=False` catches it.
  - **Override-a-pre-seeded-default** (`krutrim_agent_extensions`' security hooks) — every key already has a shipped no-op default registered at import time; an extension-source module calls `register(..., replace=True)` to swap it out.
- **`get(key)`** — raises `KeyError` (message lists every known key) if unregistered.
- **`discard(key)`** — no-op if absent; a test-only escape hatch for undoing a `discover*()`-triggered registration that `monkeypatch` can't reach (registration is an import-time side effect, and re-running a test doesn't re-import an already-imported module).
- **`discover_packages(sources)`** — for each dotted **package** path (e.g. `"krutrim_agents.profiles"`), imports it and `pkgutil.iter_modules`s over its `__path__`, importing every submodule found. Use this where a source may hold *many* implementations (dropping a new file registers a new one, zero config changes) — agent profiles are the only current user.
- **`discover_modules(sources)`** — for each dotted **module** path, imports it directly (`importlib.import_module(source)`), no `pkgutil`/`__path__` involved. Use this where each source is exactly *one* implementation — storage backends, vector-store backends, sandbox runtimes, and security-extension hooks all use this shape, since there's typically one backend per module rather than many.

Both `discover*` methods are cheap to call repeatedly (once per registry lookup is the established convention, matching `krutrim_agents_core.registry`'s own pre-existing behavior) — re-importing an already-imported module is a `sys.modules` no-op.

## 2. `atomic_write.py`

[`atomic_write.py`](../../libs/krutrim_agent_utils/src/krutrim_agent_utils/atomic_write.py) — write-to-a-`.tmp`-sibling-then-`Path.replace()`, so a concurrent reader never observes a partially-written file. This exact pattern previously existed twice, independently implemented, in `krutrim_agent_management.blobstore.LocalBlobStore.write` and `krutrim_agents_core.providers.store.ProviderStore._write` — both now call through here instead.

```python
def atomic_write_bytes(path: Path, data: bytes) -> None: ...
def atomic_write_json(
    path: Path, data: Any, *, indent: int = 2, sort_keys: bool = True
) -> None: ...
```

Both create `path.parent` if missing, write to `path.with_suffix(path.suffix + ".tmp")`, then atomically rename over `path`.

## Dependencies

[`pyproject.toml`](../../libs/krutrim_agent_utils/pyproject.toml) — package `krutrim-agent-utils`: no dependencies at all, internal or external. This is deliberate — every other package in the workspace can depend on it without pulling in anything else.

Relevant tests: exercised indirectly through `backend/tests/test_agent_registry.py` (via `krutrim_agents_core.registry`), `test_storage.py`/`test_embeddings.py` (via `krutrim_agent_management`'s factories), `test_extension_registry.py` (via `krutrim_agent_extensions.registry`).
