"""`ProxyChatModel` — a `BaseChatModel` that runs no inference of its own.

Inside the sandbox (`KRUTRIM_AGENT_RUNTIME_IN_SANDBOX=1`), `build_chat_model`
returns one of these instead of a real provider model. Every completion is a
`HostBridge.ChatComplete` gRPC call to the host (``<callback_host>:<port>``, from
`KRUTRIM_AGENT_HOST_BRIDGE_ENDPOINT`): the host rebuilds the *real* provider
model (adding the API key from its own env), streams the answer back, and logs
the call. The container's only *unfiltered* path off-box is this call-home;
direct egress, if any, is filtered by the host's `AllowlistEgressProxy`.

Only the sync `_generate` / `_stream` are implemented — that's what the graph's
model node calls via `.invoke()`. `BaseChatModel`'s default `_agenerate` /
`_astream` wrap those in an executor, which is fine here.
"""

from __future__ import annotations

import json
import os
import socket
from collections.abc import Iterator, Sequence
from typing import Any

import grpc
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.load import dumpd, load
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.messages.utils import message_chunk_to_message
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from krutrim_agent_grpc.proto import agent_runtime_pb2 as pb
from krutrim_agent_grpc.proto import agent_runtime_pb2_grpc as pbg

HOST_BRIDGE_ENDPOINT_ENV = "KRUTRIM_AGENT_HOST_BRIDGE_ENDPOINT"

#: The call-home is a gRPC control channel to the host, not agent egress — it
#: must NOT go through the container's ``HTTP(S)_PROXY`` (the allowlist egress
#: proxy), which would 403 it. gRPC otherwise honours ``http_proxy`` /
#: ``no_proxy``; this disables that per channel, independent of ``NO_PROXY``.
GRPC_CALL_HOME_OPTIONS = (("grpc.enable_http_proxy", 0),)

#: `ModelSettings` fields the sandbox must NOT dictate. It resolves them from its
#: own env, which is empty and network-isolated — so e.g. `base_url` falls back
#: to the public provider URL, bypassing a local gateway, and the real key never
#: matches. HostBridge strips these and lets the settings class re-derive them
#: from the *host* env before making the call.
HOST_OWNED_MODEL_FIELDS = ("base_url", "api_key", "api_key_env")


def host_bridge_target(endpoint: str) -> str:
    """Normalise a HostBridge endpoint to a gRPC target.

    Endpoints that already carry a gRPC scheme pass through. A bare
    ``host:port`` is resolved to an IPv4 literal (``ipv4:a.b.c.d:port``) so gRPC
    never tries an AAAA record: inside a bridge-network sandbox,
    ``host.docker.internal`` resolves to *both* the Docker Desktop IPv4 gateway
    and an unreachable ULA IPv6 address, and gRPC may pick the latter
    ("Network is unreachable"). Falls back to the original string if the host
    has no A record.
    """
    if endpoint.startswith(("ipv4:", "ipv6:", "dns:")):
        return endpoint
    host, sep, port = endpoint.rpartition(":")
    if not sep or not port.isdigit():
        return endpoint
    try:
        infos = socket.getaddrinfo(
            host.strip("[]"), int(port), socket.AF_INET, socket.SOCK_STREAM
        )
    except OSError:
        return endpoint
    return f"ipv4:{infos[0][4][0]}:{port}" if infos else endpoint


def _require_host_bridge_endpoint() -> str:
    endpoint = os.environ.get(HOST_BRIDGE_ENDPOINT_ENV)
    if not endpoint:
        raise RuntimeError(
            f"{HOST_BRIDGE_ENDPOINT_ENV} is unset — the in-sandbox runtime server "
            "sets it (from run.json) before building the graph."
        )
    return endpoint


def _host_bridge_channel():
    """A gRPC channel to the host's HostBridge. The endpoint env is a TCP
    target — ``<callback_host>:<port>`` (e.g. ``host.docker.internal:<port>``)."""
    return grpc.insecure_channel(
        host_bridge_target(_require_host_bridge_endpoint()),
        options=GRPC_CALL_HOME_OPTIONS,
    )


class ProxyChatModel(BaseChatModel):
    """Forwards completions to the host over `HostBridge.ChatComplete`."""

    model_settings_json: str
    """Keyless `ModelSettings.model_dump_json()` — the host adds credentials."""
    role: str = "main"
    """Label only — forwarded to the host purely for run-log attribution; the
    host rebuilds the model from `model_settings_json`, not the role."""

    @property
    def _llm_type(self) -> str:
        return "krutrim-agent-proxy"

    def bind_tools(
        self, tools: Sequence[Any], **kwargs: Any
    ) -> Any:
        formatted = [
            t if isinstance(t, dict) else convert_to_openai_tool(t) for t in tools
        ]
        return super().bind(tools=formatted, **kwargs)

    # -- gRPC plumbing -------------------------------------------------------

    def _chat_complete(
        self, messages: list[BaseMessage], tools: list[dict], stream: bool
    ) -> Iterator[AIMessageChunk]:
        request = pb.ChatRequest(
            role=self.role,
            messages_json=json.dumps([dumpd(m) for m in messages]),
            tools_json=json.dumps(tools) if tools else "",
            model_kwargs_json=self.model_settings_json,
            stream=stream,
        )
        with _host_bridge_channel() as channel:
            stub = pbg.HostBridgeStub(channel)
            for chunk in stub.ChatComplete(request):
                if chunk.error:
                    raise RuntimeError(f"HostBridge.ChatComplete failed: {chunk.error}")
                if chunk.chunk_json:
                    loaded = load(json.loads(chunk.chunk_json))
                    if isinstance(loaded, AIMessageChunk):
                        yield loaded
                    else:  # a full AIMessage came back (stream=False path)
                        yield AIMessageChunk(
                            content=loaded.content,
                            additional_kwargs=getattr(loaded, "additional_kwargs", {}),
                            response_metadata=getattr(loaded, "response_metadata", {}),
                            tool_call_chunks=[
                                {
                                    "name": tc["name"],
                                    "args": json.dumps(tc["args"]),
                                    "id": tc.get("id"),
                                    "index": i,
                                }
                                for i, tc in enumerate(getattr(loaded, "tool_calls", []))
                            ],
                            usage_metadata=getattr(loaded, "usage_metadata", None),
                            id=getattr(loaded, "id", None),
                        )
                if chunk.done:
                    break

    # -- BaseChatModel hooks ----------------------------------------------

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        tools = kwargs.get("tools") or []
        for chunk in self._chat_complete(messages, tools, stream=True):
            if run_manager and chunk.content:
                run_manager.on_llm_new_token(str(chunk.content), chunk=None)
            yield ChatGenerationChunk(message=chunk)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        tools = kwargs.get("tools") or []
        merged: AIMessageChunk | None = None
        for chunk in self._chat_complete(messages, tools, stream=True):
            merged = chunk if merged is None else merged + chunk
        if merged is None:
            merged = AIMessageChunk(content="")
        return ChatResult(
            generations=[ChatGeneration(message=message_chunk_to_message(merged))]
        )


def build_proxy_chat_model(settings: Any) -> ProxyChatModel:
    """Called from `krutrim_agents_core.providers.registry.build_chat_model`
    when running in-sandbox. `settings` is a `ModelSettings` (or subclass).
    The HostBridge endpoint is read per-call from the env (`_host_bridge_channel`)."""
    if not os.environ.get(HOST_BRIDGE_ENDPOINT_ENV):
        raise RuntimeError(
            f"{HOST_BRIDGE_ENDPOINT_ENV} is unset — the in-sandbox runtime server "
            "sets it before building the graph."
        )
    return ProxyChatModel(
        model_settings_json=settings.model_dump_json(
            exclude=set(HOST_OWNED_MODEL_FIELDS)
        )
    )
