"""Drop-in replacements for the host-side tools (`web_search`, `fetch_url`,
`rag_tool`) that forward to `HostBridge.InvokeHostTool` instead of touching the
network. Same tool names / arg schema / descriptions, so the model sees no
difference.

Selected by `KRUTRIM_AGENT_RUNTIME_IN_SANDBOX=1` — see the guarded imports in
`krutrim_agents_core.tools` and `krutrim_agent_rag.tool`.

Each tool exposes **both** a sync and an async implementation (like
`ProxyChatModel`): a graph node that invokes tools synchronously — the research
profile's hand-rolled `ToolNode` + `wrap_tool_call` path does — would otherwise
hit "StructuredTool does not support sync invocation".
"""

from __future__ import annotations

import json
import os

import grpc
from langchain_core.tools import StructuredTool

from krutrim_agent_grpc.proto import agent_runtime_pb2 as pb
from krutrim_agent_grpc.proto import agent_runtime_pb2_grpc as pbg
from krutrim_agent_grpc.proxy_model import (
    GRPC_CALL_HOME_OPTIONS,
    HOST_BRIDGE_ENDPOINT_ENV,
    host_bridge_target,
)


def _thread_id() -> str:
    try:
        from langgraph.config import get_config

        return (get_config().get("configurable") or {}).get("thread_id", "") or ""
    except Exception:  # noqa: BLE001 - outside a graph run there is no config
        return ""


def _request(name: str, args: dict) -> pb.HostToolRequest:
    return pb.HostToolRequest(
        tool=name, args_json=json.dumps(args), thread_id=_thread_id()
    )


def _format_reply(name: str, reply: pb.HostToolReply) -> str:
    if reply.error:
        return f"Error: {reply.error}"
    try:
        result = json.loads(reply.result_json)
    except json.JSONDecodeError:
        return reply.result_json
    return result if isinstance(result, str) else json.dumps(result)


async def _invoke_host_tool(name: str, args: dict) -> str:
    endpoint = os.environ.get(HOST_BRIDGE_ENDPOINT_ENV)
    if not endpoint:
        return f"Error: {name} unavailable — {HOST_BRIDGE_ENDPOINT_ENV} is unset."
    try:
        async with grpc.aio.insecure_channel(
            host_bridge_target(endpoint), options=GRPC_CALL_HOME_OPTIONS
        ) as channel:
            reply = await pbg.HostBridgeStub(channel).InvokeHostTool(
                _request(name, args), timeout=120.0
            )
    except grpc.aio.AioRpcError as exc:
        return f"Error: {name} call to host failed ({exc.details()})."
    return _format_reply(name, reply)


def _invoke_host_tool_sync(name: str, args: dict) -> str:
    endpoint = os.environ.get(HOST_BRIDGE_ENDPOINT_ENV)
    if not endpoint:
        return f"Error: {name} unavailable — {HOST_BRIDGE_ENDPOINT_ENV} is unset."
    try:
        with grpc.insecure_channel(
            host_bridge_target(endpoint), options=GRPC_CALL_HOME_OPTIONS
        ) as channel:
            reply = pbg.HostBridgeStub(channel).InvokeHostTool(
                _request(name, args), timeout=120.0
            )
    except grpc.RpcError as exc:
        detail = exc.details() if hasattr(exc, "details") else str(exc)
        return f"Error: {name} call to host failed ({detail})."
    return _format_reply(name, reply)


# -- the tools -----------------------------------------------------------------
# One StructuredTool per host tool, carrying both `func` (sync) and `coroutine`
# (async) so either invocation path works.


def _web_search_sync(query: str) -> str:
    return _invoke_host_tool_sync("web_search", {"query": query})


async def _web_search_async(query: str) -> str:
    return await _invoke_host_tool("web_search", {"query": query})


def _fetch_url_sync(url: str) -> str:
    return _invoke_host_tool_sync("fetch_url", {"url": url})


async def _fetch_url_async(url: str) -> str:
    return await _invoke_host_tool("fetch_url", {"url": url})


def _rag_tool_sync(query: str) -> str:
    return _invoke_host_tool_sync("rag", {"query": query})


async def _rag_tool_async(query: str) -> str:
    return await _invoke_host_tool("rag", {"query": query})


web_search = StructuredTool.from_function(
    func=_web_search_sync,
    coroutine=_web_search_async,
    name="web_search",
    description=(
        "Search the web and return titles, URLs, and snippets for the top "
        "results. Use this to find current information you don't already have."
    ),
)

fetch_url = StructuredTool.from_function(
    func=_fetch_url_sync,
    coroutine=_fetch_url_async,
    name="fetch_url",
    description=(
        "Fetch a web page and return its content as plain text/markdown. Use "
        "this to read a specific source in full after finding it via "
        "`web_search` (or when the user gives you a URL directly)."
    ),
)

rag_tool = StructuredTool.from_function(
    func=_rag_tool_sync,
    coroutine=_rag_tool_async,
    name="rag_tool",
    description=(
        "Search documents the user has attached to this session and return the "
        "most relevant passages. Use this before web search when the answer is "
        "likely in the user's own uploaded material."
    ),
)


def build_message_agent_proxy():
    """The in-sandbox stand-in for `krutrim_agents_core.cross_agent.message_agent`.

    The real tool needs the full `Storage` / `ProviderStore` / `SandboxRegistry`
    (none of which exist in the container), so the whole exchange runs on the
    host: this forwards to `HostBridge.InvokeHostTool("message_agent", ...)`,
    where `agent_run.py` has wired a handler bound to the calling session's
    identity and an empty call chain. Only attached when the host told the
    runtime this session has an eligible peer (`cross_agent_enabled`).
    """

    def _sync(container_id: str, message: str) -> str:
        return _invoke_host_tool_sync(
            "message_agent", {"container_id": container_id, "message": message}
        )

    async def _async(container_id: str, message: str) -> str:
        return await _invoke_host_tool(
            "message_agent", {"container_id": container_id, "message": message}
        )

    return StructuredTool.from_function(
        func=_sync,
        coroutine=_async,
        name="message_agent",
        description=(
            "Send a message to another agent session in this project and get "
            "its reply. `container_id` is the target session's id. Only works "
            "if this session's sharing policy makes you and the target mutually "
            "eligible to message each other."
        ),
    )
