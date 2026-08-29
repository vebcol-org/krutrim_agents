"""Application-wide settings, loaded from environment variables / .env."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from krutrim_agent_management.paths import default_storage_root


def _find_backend_root(start: Path) -> Path:
    """Walks up from `start` for the `backend/` checkout root (holds `harness/` and `.env`)."""
    for candidate in (start, *start.parents):
        if (candidate / "harness").is_dir():
            return candidate
    return start


BACKEND_ROOT = _find_backend_root(Path(__file__).resolve())


def _env_files() -> tuple[Path, ...]:
    """Ordered dotenv paths, lowest priority first.

    Always `<BACKEND_ROOT>/.env`, then an optional environment-specific file
    named by KRUTRIM_AGENT_ENV_FILE (e.g. `.env.dev`, `.env.prod`). That var
    must come from the real environment — a shell export or the docker-compose
    `environment:` block — it cannot live in the file it selects. A relative
    value resolves against BACKEND_ROOT; a missing file is skipped.
    """
    files = []
    override = os.getenv("KRUTRIM_AGENT_ENV_FILE", "").strip()
    if override:
        candidate = Path(override)
        files.append(candidate if candidate.is_absolute() else BACKEND_ROOT / candidate)
    if not files:
        files.append(BACKEND_ROOT / ".env")
    return tuple(files)


ENV_FILES = _env_files()

# unprefixed fields (DEV_MODE, Langfuse keys) are read via os.getenv, so the
# dotenv files must be loaded manually here. Load the most specific file FIRST:
# with override=False the first loader of a key wins and an already-set real env
# var beats them all — giving precedence OS env > .env.dev > .env.
for _env_path in reversed(ENV_FILES):
    load_dotenv(_env_path)


def _get_redis_url() -> str:
    """Builds a Redis URL from env vars; REDIS_URL overrides everything else if set."""
    direct_url = os.getenv("REDIS_URL")
    if direct_url:
        return direct_url

    user = os.getenv("REDIS_USER", "")
    password = os.getenv("REDIS_PASSWORD", "")
    host = os.getenv("REDIS_HOST", "localhost")
    port = os.getenv("REDIS_PORT", "6379")
    db = os.getenv("REDIS_DB", "0")
    use_tls = os.getenv("REDIS_USE_TLS", "false").lower() == "true"

    scheme = "rediss" if use_tls else "redis"

    if user and password:
        auth = f"{user}:{password}@"
    elif password:
        auth = f":{password}@"
    else:
        auth = ""

    return f"{scheme}://{auth}{host}:{port}/{db}"


class AppSettings(BaseSettings):
    # env_prefix: every field below is read from KRUTRIM_AGENT_<FIELD> (case-
    # insensitive) — pydantic-settings strips the prefix and assigns. Fields
    # that also accept an UNPREFIXED name (DEV_MODE, LANGFUSE_*, REDIS_*) do it
    # explicitly via a default_factory / os.getenv below.
    # env_file: pydantic applies these low-priority (a real env var always wins)
    # and last-wins across the tuple — so .env.dev overrides .env. See _env_files().
    model_config = SettingsConfigDict(
        env_prefix="krutrim_agent_",
        env_file=ENV_FILES,
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000

    harness_dir: Path = BACKEND_ROOT / "harness"
    sandbox_image: str = "krutrim_agent-sandbox:latest"
    # sandbox backend registry — "docker" is the only implementation today
    sandbox_runtime: str = "docker"
    sandbox_runtime_sources: list[str] = ["krutrim_agent_sandbox.docker_backend"]

    # LangGraph super-step cap for a single agent turn — raise it for deep
    # multi-tool / subagent research loops that legitimately need many steps.
    # `krutrim_agent_agui.translator` reads the same env var directly (so it
    # applies in the sandbox too, exported from RunConfig by the grpc server).
    graph_recursion_limit: int = 100

    # Automatic context management so a long turn doesn't blow the model's
    # context window (`build_context_management_middleware`):
    #   "off"       — nothing (default)
    #   "trim"      — LangChain ContextEditingMiddleware: clears the oldest tool
    #                 outputs once the window fills. Cheap, no extra LLM call.
    #   "summarize" — LangChain SummarizationMiddleware: replaces old messages
    #                 with an LLM-written summary once the running message total
    #                 passes `..._trigger_tokens`, keeping the last
    #                 `..._keep_messages`.
    #   "rag"       — reserved; not implemented yet, falls back to "summarize".
    # An absolute token trigger (not a fraction) so it works for models whose
    # LangChain profile doesn't advertise a context window (proxied / OpenRouter).
    context_management_strategy: str = "off"
    context_trigger_tokens: int = 120_000
    context_keep_messages: int = 20

    # Per-profile opt-in to running the whole agent graph inside the sandbox
    # container over gRPC (see krutrim_agent_grpc). Others keep the in-process
    # tool-backend path. `research` is the first profile enabled here.
    in_sandbox_agent_profiles: list[str] = ["research"]
    # Addressing for the in-sandbox runtime's TCP gRPC (host <-> container).
    # Defaults suit a backend process running directly on a Docker Desktop host;
    # override all three for a containerised backend, or for a non-Docker runtime
    # (k8s, a cloud sandbox service) where the runtime port is reached by a
    # routable name.
    #   bind_host     — interface the per-turn HostBridge, allowlist egress
    #                   proxy, and the published sandbox runtime port bind to.
    #   dial_host     — host address the backend dials to reach that published
    #                   sandbox runtime port (`_resolve_run_endpoint`).
    #   callback_host — address the sandbox container dials to reach back to the
    #                   host's HostBridge / egress proxy.
    sandbox_bind_host: str = "127.0.0.1"
    sandbox_dial_host: str = "127.0.0.1"
    sandbox_callback_host: str = "host.docker.internal"
    # User-defined Docker network to attach in-sandbox containers to. None → the
    # default bridge, backend and sandbox talk over the host (dial_host /
    # callback_host). Set to the backend's own compose network (e.g.
    # "krutrim-agent-dev_default") for a containerised backend: the two then
    # reach each other by container name on that network — no host port
    # publishing — so pair it with
    #   sandbox_dial_host      = (ignored; the sandbox container name is used)
    #   sandbox_callback_host  = the backend's service alias on that network
    sandbox_network: str | None = None
    # How long to wait for a freshly-started in-sandbox AgentRuntime to answer
    # Health before giving up. The first `docker run` of a newly-built image on
    # macOS Docker Desktop (materializing the venv layer into the VM + vpnkit
    # port setup) can take over a minute; warm starts are ~1s.
    sandbox_runtime_health_timeout: float = 120.0
    # Optional read-only bind mount of the repo's agent source over the image's
    # baked copy, for local iteration without an image rebuild.
    sandbox_agent_source_dir: Path | None = None
    # Hosts an in-sandbox container may reach *directly* (exact or dot-suffix
    # match, e.g. "example.com" also allows "api.example.com"). The container
    # always runs behind the host's AllowlistEgressProxy (HTTP(S)_PROXY); this
    # list is what the proxy forwards. Empty (default) = deny-all: the only
    # unfiltered path off-box is the audited HostBridge call-home.
    sandbox_egress_allowlist: list[str] = []
    # Overrides `runs_dir` (default `harness/memory/runs`) — the in-sandbox
    # runtime points this at the bind-mounted `out/runs` so RunLogger
    # transcripts survive the container.
    runs_dir_override: Path | None = None

    # runtime data (projects, sessions, checkpoints, ...); override via KRUTRIM_AGENT_STORAGE_ROOT
    storage_root: Path = Field(default_factory=default_storage_root)
    
    # Default Model settings
    default_model: str = "deepseek/deepseek-v4-flash-0731" 

    # Storage backend registry — "local" (SQLite + filesystem) is the only implementation today
    storage_backend: str = "local"
    storage_backend_sources: list[str] = ["krutrim_agent_management.local"]

    # VectorStore backend registry — "faisslite" (default) or "qdrant"
    vector_store_backend: str = "faisslite"
    vector_store_backend_sources: list[str] = [
        "krutrim_agent_rag.embeddings",
        "krutrim_agent_rag.qdrant_store",
    ]

    # Qdrant connection settings — only read when vector_store_backend="qdrant"
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_prefer_grpc: bool = False
    qdrant_https: bool = False
    # ":memory:" for tests/local dev without a running Qdrant server; overrides qdrant_url when set
    qdrant_location: str | None = None

    # TAVILY_API_KEY and generally returns higher-quality results.
    web_search_provider: str = "tavily"

    # Rag settings
    rag_embedding_model: str = "qwen/qwen3-embedding-8b"
    retrieval_strategy: str = "vector_only"
    retrieval_strategy_sources: list[str] = ["krutrim_agent_rag.retrieval_strategy"]
    rag_injection_enabled: bool = False

    cors_origins: list[str] = []

    # ── Logging ─────────────────────────────────────────────────────────
    # One shared config for every process (see
    # krutrim_agent_management.logging_config.configure_logging). The FastAPI
    # server writes <log_dir>/server/server.log and the Celery worker writes
    # <log_dir>/worker/worker.log — same knobs, different sink. Overridable
    # with the KRUTRIM_AGENT_LOG_* env vars (see .env.example).
    log_dir: Path = Field(default_factory=lambda: default_storage_root() / "logs")
    # File-sink threshold. INFO by default; .env.dev raises it to DEBUG (and
    # dev_mode forces DEBUG regardless, so both console + file get the verbose
    # step-by-step trace during local development).
    log_level: str = "INFO"
    # stderr threshold; forced to DEBUG whenever dev_mode is on.
    log_console_level: str = "INFO"
    # loguru rotation trigger — a duration ("1 day"), a clock time ("00:00"),
    # or a size ("20 MB"). "1 day" = a fresh periodic file every 24h.
    log_rotation: str = "1 day"
    # how long rotated files are kept before loguru deletes them.
    log_retention: str = "14 days"
    # "" keeps rotated files as-is; "zip"/"gz"/"tar.gz"/... compresses them.
    log_compression: str = ""
    # extended (variable-free) tracebacks in the file sink; also on when dev_mode.
    log_backtrace: bool = False
    # route stdlib logging (uvicorn / celery / httpx / ...) through loguru so
    # everything lands in the same rotating files with one format.
    log_intercept_std: bool = True

    # celery broker/result-backend
    redis_url: str = Field(default_factory=lambda: _get_redis_url())

    # max wait on a peer's turn via the cross-agent `message_agent` tool
    cross_agent_call_timeout_seconds: int = 60

    # dotted packages scanned for AgentProfile plugins; OSS profiles always included
    agent_profile_sources: list[str] = ["krutrim_agents.profiles"]

    # "community" or "extended" — gates the startup selfcheck, not a feature flag
    edition: str = "community"

    # dotted modules overriding the no-op RequestAuthenticator/AgentVisibilityPolicy/AuditSink
    extension_sources: list[str] = []

    # KRUTRIM_AGENT_DEV_MODE (prefixed) wins; a bare DEV_MODE also works, read
    # here since env_prefix would otherwise hide it.
    dev_mode: bool = Field(
        default_factory=lambda: os.getenv("DEV_MODE", "").strip().lower()
        in ("1", "true", "yes", "on")
    )

    # Master off-switch for Langfuse tracing (KRUTRIM_AGENT_LANGFUSE_ENABLED).
    # Even in dev_mode with keys set, flip this false where the collector is
    # unreachable (e.g. a containerised backend whose LANGFUSE_BASE_URL points
    # at a host not running Langfuse) to stop the OTEL exporter error spam.
    langfuse_enabled: bool = True

    # Langfuse tracing, only active when dev_mode is on; unprefixed to match the SDK's own env vars
    langfuse_public_key: str | None = Field(
        default_factory=lambda: os.getenv("LANGFUSE_PUBLIC_KEY")
    )
    langfuse_secret_key: str | None = Field(
        default_factory=lambda: os.getenv("LANGFUSE_SECRET_KEY")
    )
    # LANGFUSE_BASE_URL takes priority (self-hosted); LANGFUSE_HOST is the older/cloud-default fallback
    langfuse_host: str | None = Field(
        default_factory=lambda: (
            os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST")
        )
    )

    @property
    def skills_dir(self) -> Path:
        return self.harness_dir / "skills"

    @property
    def common_skills_dir(self) -> Path:
        return self.skills_dir / "common"

    def agent_skills_dir(self, agent_key: str) -> Path:
        return self.skills_dir / agent_key

    @property
    def prompts_root_dir(self) -> Path:
        return self.harness_dir / "prompts"

    def prompts_dir(self, folder_name: str) -> Path:
        return self.prompts_root_dir / folder_name

    @property
    def memory_dir(self) -> Path:
        return self.harness_dir / "memory"

    def agent_memory_dir(self, agent_key: str) -> Path:
        return self.memory_dir / agent_key

    @property
    def evals_dir(self) -> Path:
        return self.harness_dir / "evals"

    @property
    def provider_settings_path(self) -> Path:
        return self.memory_dir / "settings.json"

    @property
    def runs_dir(self) -> Path:
        return self.runs_dir_override or (self.memory_dir / "runs")


settings = AppSettings()
