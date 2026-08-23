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

# unprefixed fields (DEV_MODE, Langfuse keys) read via os.getenv need .env loaded manually
load_dotenv(BACKEND_ROOT / ".env")


def _env_flag(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


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
    model_config = SettingsConfigDict(
        env_prefix="KRUTRIM_AGENT_", env_file=".env", extra="ignore"
    )

    host: str = "0.0.0.0"
    port: int = 8000

    harness_dir: Path = BACKEND_ROOT / "harness"
    sandbox_image: str = "krutrim_agent-sandbox:latest"
    # sandbox backend registry — "docker" is the only implementation today
    sandbox_runtime: str = "docker"
    sandbox_runtime_sources: list[str] = ["krutrim_agent_sandbox.docker_backend"]

    # runtime data (projects, sessions, checkpoints, ...); override via KRUTRIM_AGENT_STORAGE_ROOT
    storage_root: Path = Field(default_factory=default_storage_root)

    # Storage backend registry — "local" (SQLite + filesystem) is the only implementation today
    storage_backend: str = "local"
    storage_backend_sources: list[str] = ["krutrim_agent_management.local"]

    # VectorStore backend registry — "faisslite" is the only implementation today
    vector_store_backend: str = "faisslite"
    vector_store_backend_sources: list[str] = ["krutrim_agent_rag.embeddings"]

    # Web search tool provider — "duckduckgo" needs no API key; "tavily" needs
    # TAVILY_API_KEY and generally returns higher-quality results.
    web_search_provider: str = "tavily"

    # OpenRouter-hosted embedding model used for RAG ingestion (krutrim_agent_rag,
    # krutrim_agent_celery's precompute_embeddings/process_rag_document tasks).
    # Requires OPENROUTER_API_KEY. Chosen for low per-token cost.
    rag_embedding_model: str = "qwen/qwen3-embedding-8b"

    cors_origins: list[str] = [
        "http://localhost:4200",
        "http://localhost:5173",
        "http://localhost:4300",
    ]

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

    # falls back to unprefixed DEV_MODE if KRUTRIM_AGENT_DEV_MODE isn't set
    dev_mode: bool = Field(default_factory=lambda: _env_flag("DEV_MODE"))

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
        return self.memory_dir / "runs"


settings = AppSettings()
