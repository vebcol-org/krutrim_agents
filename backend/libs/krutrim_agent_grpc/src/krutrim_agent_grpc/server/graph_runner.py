"""Build the agent graph *inside the sandbox* and stream one turn as AG-UI
event-JSON strings.

Profile-agnostic: it calls the same `krutrim_agents_core.builder.build_agent`
the host used to call, just with a `LocalShellBackend` (real local shell + FS,
confined to the container) instead of a `DockerSandboxBackend`. Skills / memory
come from the read-only harness subset bind-mounted at
`$KRUTRIM_AGENT_HARNESS_DIR`. Every LLM/tool call inside the graph is already
routed to the host by the `KRUTRIM_AGENT_RUNTIME_IN_SANDBOX` guards in
`krutrim_agents_core` — see `proxy_model` / `proxy_tools`.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from krutrim_agent_grpc.run_config import RunConfig


async def stream_turn(
    cfg: RunConfig,
    *,
    thread_id: str,
    run_id: str,
    user_message: str,
    frontend_tools_json: str,
    cross_agent_enabled: bool = False,
) -> AsyncIterator[str]:
    # Deferred imports: the servicer sets the env (harness dir, storage root,
    # host-bridge socket) before this module touches `krutrim_agent_management.config`.
    from ag_ui.core.types import RunAgentInput, Tool, UserMessage
    from deepagents.backends import LocalShellBackend
    from krutrim_agent_agui import run_graph_as_agui
    from krutrim_agents_core.builder import build_agent
    from krutrim_agents_core.harness.run_logging import RunLoggingMiddleware
    from krutrim_agents_core.harness.runs import RunLogger
    from krutrim_agents_core.providers.store import ProviderStore
    from krutrim_agents_core.registry import get_profile
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    from krutrim_agent_grpc.proxy_tools import build_message_agent_proxy

    profile = get_profile(cfg.agent_key)
    provider_store = ProviderStore(Path(cfg.provider_settings_path))

    tool_defs = json.loads(frontend_tools_json) if frontend_tools_json else []
    input_data = RunAgentInput(
        thread_id=thread_id,
        run_id=run_id or uuid.uuid4().hex,
        state={},
        messages=[UserMessage(id=uuid.uuid4().hex, role="user", content=user_message)],
        tools=[Tool.model_validate(t) for t in tool_defs],
        context=[],
        forwarded_props={},
    )

    # root_dir="/" + virtual_mode=False → the agent's own absolute paths
    # (e.g. the research profile's /workspace/.research/state.md) are real paths
    # inside this container, exactly as they were inside the Docker sandbox before.
    backend = LocalShellBackend(root_dir="/", virtual_mode=False)

    # Every model/tool call inside the graph is teed into the same per-run
    # JSONL the servicer and HostBridge write to; `out/runs/<thread>.jsonl`
    # is folded back into the session dir by `Storage.import_scope`.
    run_logger = RunLogger(
        cfg.agent_key,
        thread_id,
        path=Path(cfg.runs_dir) / f"{thread_id}.jsonl",
    )
    extra_middleware = [RunLoggingMiddleware(run_logger)]

    extra_tools = [build_message_agent_proxy()] if cross_agent_enabled else []

    Path(cfg.checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(cfg.checkpoint_path) as checkpointer:
        graph = build_agent(
            profile,
            provider_store,
            backend,
            checkpointer=checkpointer,
            extra_tools=extra_tools,
            extra_middleware=extra_middleware,
        )
        async for event in run_graph_as_agui(graph, input_data, thread_id=thread_id):
            # Mirror `ag_ui.encoder.EventEncoder`: `exclude_none` so unset
            # optionals (timestamp, parentRunId, input, rawEvent) are omitted
            # rather than serialized as `null` — the host streams this string to
            # the browser verbatim, and @ag-ui/client's `.optional()` Zod
            # schemas reject `null`.
            yield event.model_dump_json(by_alias=True, exclude_none=True)
