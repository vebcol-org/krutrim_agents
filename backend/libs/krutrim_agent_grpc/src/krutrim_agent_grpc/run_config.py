"""`run.json` — the per-run config the host writes into the staging dir and the
in-sandbox runtime reads on startup. Deliberately carries **no credentials**:
model settings here are the keyless `ModelSettings` shape (provider + model +
sampling params + the *name* of the env var a key would come from), and the
sandbox never has that env var. The host's `HostBridge.ChatComplete` is what
adds the real key when it makes the actual call.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

RUN_CONFIG_NAME = "run.json"


class RunConfig(BaseModel):
    agent_key: str
    agent_id: str
    project_id: str
    session_id: str
    """Also the AG-UI/LangGraph ``thread_id``."""

    # Container-side paths (all under the single bind-mounted staging dir).
    storage_root: str = "/run/krutrim_agent/store"
    harness_dir: str = "/run/krutrim_agent/harness"
    workspace_dir: str = "/workspace"
    out_dir: str = "/run/krutrim_agent/out"
    checkpoint_path: str = "/run/krutrim_agent/out/langgraph_checkpoint.sqlite"
    provider_settings_path: str = "/run/krutrim_agent/provider_settings.json"
    """Keyless per-`(agent_key, role)` model settings the host filtered down to
    this one agent. Absent → `ProviderStore` seeds from profile defaults."""
    runs_dir: str = "/run/krutrim_agent/out/runs"

    # -- transport (always TCP gRPC) -----------------------------------
    runtime_bind: str = "0.0.0.0:50051"
    """Where the in-container AgentRuntime server binds — always a TCP address.
    The port is published to the host (or reached by container name on a shared
    Docker network)."""
    host_bridge_dial: str = "host.docker.internal:50051"
    """``host:port`` the container's proxy model/tools dial to reach the host's
    HostBridge. Set per-run by `SandboxRegistry` (``<callback_host>:<port>``)."""

    role_models: dict[str, dict] = {}
    """``{role: keyless ModelSettings dict}`` for every role the profile uses
    (``main``/``researcher``/``critic``/``writer`` for research). The runtime
    passes the matching dict straight through to ``HostBridge.ChatComplete``."""

    recursion_limit: int = 100

    def write(self, staging_dir: Path) -> Path:
        path = Path(staging_dir) / RUN_CONFIG_NAME
        path.write_text(json.dumps(self.model_dump(), indent=2))
        return path

    @classmethod
    def read(cls, staging_dir: Path | str) -> RunConfig:
        path = Path(staging_dir) / RUN_CONFIG_NAME
        return cls.model_validate_json(path.read_text())
