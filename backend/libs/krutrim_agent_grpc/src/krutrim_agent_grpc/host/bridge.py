"""`HostBridgeServicer` + `serve_host_bridge` — run on the host for one turn.

`ChatComplete` rebuilds the real provider model (the host's env has the API
key; `KRUTRIM_AGENT_RUNTIME_IN_SANDBOX` is unset here) and streams it back.
`InvokeHostTool` runs the real `web_search` / `fetch_url` / `rag_tool`. Both
append a line to the run's JSONL transcript — this is the single point where
every outbound call the sandboxed agent makes is observed.
"""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import grpc
from loguru import logger

from krutrim_agent_grpc.proto import agent_runtime_pb2 as pb
from krutrim_agent_grpc.proto import agent_runtime_pb2_grpc as pbg
from krutrim_agent_grpc.proxy_model import HOST_OWNED_MODEL_FIELDS

MessageAgentHandler = Callable[[str, str], Awaitable[str]]
"""`(target_session_id, message) -> reply` — the host-side `message_agent`.
`agent_run.py` binds it to the calling session's identity + an empty call
chain before handing it to `serve_host_bridge`."""


class _RunTranscript:
    """Minimal append-only JSONL writer — same shape as
    `krutrim_agents_core.harness.runs.RunLogger`, but pointed at an explicit
    path so host + sandbox logs land in the same session directory."""

    def __init__(self, path: Path | None) -> None:
        self._path = path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event_type: str, payload: dict[str, Any]) -> None:
        if self._path is None:
            return
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "source": "host_bridge",
            "type": event_type,
            **payload,
        }
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")


class HostBridgeServicer(pbg.HostBridgeServicer):
    def __init__(
        self,
        *,
        thread_id: str,
        transcript_path: Path | None = None,
        on_usage=None,
        message_agent_handler: MessageAgentHandler | None = None,
    ) -> None:
        self._thread_id = thread_id
        self._transcript = _RunTranscript(transcript_path)
        # optional callback(dict) invoked with each turn's usage_metadata, so
        # agent_run.py can fold token counts into usage.json / a CUSTOM event.
        self._on_usage = on_usage
        # optional host-side `message_agent`; only set for a session whose
        # sharing policy makes at least one sibling agent reachable.
        self._message_agent_handler = message_agent_handler

    async def ChatComplete(
        self, request: pb.ChatRequest, context
    ) -> AsyncIterator[pb.ChatChunk]:
        from krutrim_agents_core.providers.registry import (
            build_chat_model,
            parse_model_settings,
        )
        from langchain_core.load import dumpd, load

        started = time.monotonic()
        try:
            raw_settings = json.loads(request.model_kwargs_json)
            # base_url / credentials are the host's to decide — the sandbox
            # resolves them from its own empty env. Drop whatever it sent so the
            # settings class re-derives them here (build_proxy_chat_model already
            # omits them; this is defence against a tampered payload).
            for _field in HOST_OWNED_MODEL_FIELDS:
                raw_settings.pop(_field, None)
            settings = parse_model_settings(raw_settings)
            model = build_chat_model(settings)
            if request.tools_json:
                model = model.bind_tools(json.loads(request.tools_json))
            messages = [load(d) for d in json.loads(request.messages_json)]
        except Exception as exc:  # noqa: BLE001
            logger.exception("HostBridge.ChatComplete setup failed")
            yield pb.ChatChunk(done=True, error=f"{type(exc).__name__}: {exc}")
            return

        self._transcript.log(
            "chat_request",
            {
                "role": request.role,
                "model": getattr(settings, "model", None),
                "messages": len(messages),
                "tools": bool(request.tools_json),
            },
        )

        usage: dict[str, Any] | None = None
        text_len = 0
        try:
            async for chunk in model.astream(messages):
                text_len += len(chunk.content or "")
                if getattr(chunk, "usage_metadata", None):
                    usage = dict(chunk.usage_metadata)
                yield pb.ChatChunk(chunk_json=json.dumps(dumpd(chunk)))
        except Exception as exc:  # noqa: BLE001
            logger.exception("HostBridge.ChatComplete stream failed")
            yield pb.ChatChunk(done=True, error=f"{type(exc).__name__}: {exc}")
            return

        yield pb.ChatChunk(done=True)
        self._transcript.log(
            "chat_response",
            {
                "model": getattr(settings, "model", None),
                "chars": text_len,
                "usage": usage,
                "latency_ms": round((time.monotonic() - started) * 1000),
            },
        )
        if usage and self._on_usage is not None:
            with contextlib.suppress(Exception):
                self._on_usage(usage)


    async def InvokeHostTool(
        self, request: pb.HostToolRequest, context
    ) -> pb.HostToolReply:
        started = time.monotonic()
        try:
            args = json.loads(request.args_json) if request.args_json else {}
        except json.JSONDecodeError as exc:
            return pb.HostToolReply(error=f"bad args_json: {exc}")

        if request.tool == "message_agent":
            if self._message_agent_handler is None:
                return pb.HostToolReply(
                    error="message_agent is not available for this session"
                )
            self._transcript.log(
                "tool_call",
                {"tool": "message_agent", "target": args.get("container_id")},
            )
            try:
                reply = await self._message_agent_handler(
                    str(args.get("container_id", "")), str(args.get("message", ""))
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("HostBridge.InvokeHostTool message_agent failed")
                return pb.HostToolReply(error=f"{type(exc).__name__}: {exc}")
            self._transcript.log(
                "tool_result",
                {
                    "tool": "message_agent",
                    "chars": len(reply) if isinstance(reply, str) else None,
                    "latency_ms": round((time.monotonic() - started) * 1000),
                },
            )
            return pb.HostToolReply(result_json=json.dumps(reply))

        tool = _resolve_host_tool(request.tool)
        if tool is None:
            return pb.HostToolReply(error=f"unknown host tool {request.tool!r}")

        self._transcript.log("tool_call", {"tool": request.tool, "args": args})
        try:
            result = await _run_host_tool(tool, request.tool, args, request.thread_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("HostBridge.InvokeHostTool {} failed", request.tool)
            return pb.HostToolReply(error=f"{type(exc).__name__}: {exc}")

        self._transcript.log(
            "tool_result",
            {
                "tool": request.tool,
                "chars": len(result) if isinstance(result, str) else None,
                "latency_ms": round((time.monotonic() - started) * 1000),
            },
        )
        return pb.HostToolReply(result_json=json.dumps(result))

    async def Health(self, request, context):
        return pb.HealthReply(ready=True)


def _resolve_host_tool(name: str):
    from krutrim_agents_core.tools import fetch_url, web_search

    if name == "web_search":
        return web_search
    if name == "fetch_url":
        return fetch_url
    if name == "rag":
        try:
            from krutrim_agent_rag.tool import rag_tool

            return rag_tool
        except Exception:  # noqa: BLE001 - rag optional
            return None
    return None


async def _run_host_tool(tool, name: str, args: dict, thread_id: str):
    # rag_tool reads its session id from the LangGraph run config's thread_id;
    # there's no graph here, so scope it explicitly instead.
    if name == "rag":
        from langchain_core.runnables import RunnableConfig

        cfg = RunnableConfig(configurable={"thread_id": thread_id})
        return await tool.ainvoke(args, config=cfg)
    return await tool.ainvoke(args)


@contextlib.asynccontextmanager
async def serve_host_bridge(
    bind: str,
    *,
    thread_id: str,
    transcript_path: Path | None = None,
    on_usage=None,
    message_agent_handler: MessageAgentHandler | None = None,
):
    """Start a HostBridge gRPC server for the duration of the `async with`
    block. `bind` is a TCP gRPC target ``<bind_host>:<port>`` — the port is
    pre-allocated per run by `SandboxRegistry`."""
    server = grpc.aio.server()
    pbg.add_HostBridgeServicer_to_server(
        HostBridgeServicer(
            thread_id=thread_id,
            transcript_path=transcript_path,
            on_usage=on_usage,
            message_agent_handler=message_agent_handler,
        ),
        server,
    )
    server.add_insecure_port(bind)
    await server.start()
    try:
        yield server
    finally:
        await server.stop(grace=2)
