"""A host-side allowlisting HTTP forward proxy for `SandboxPolicy.network ==
"egress-allowlist"`.

The in-sandbox runtime's default posture is `network="none"` — every LLM/tool
call is a gRPC call-home through `HostBridge`, which is the sole egress point
and audit trail. `"egress-allowlist"` is the middle ground for a sandbox that
genuinely needs to reach a *small, fixed* set of hosts directly (a private
package index, an internal API) without opening general networking: the
container runs on a normal bridge network but with `HTTP(S)_PROXY` pointed at
this proxy, which only forwards connections whose host matches
`SandboxPolicy.egress_allowlist` and refuses (HTTP 403) everything else. Every
allow/deny decision is handed to `on_event` for logging.

It speaks just enough HTTP/1.1 to be a proxy:

- ``CONNECT host:port`` — the tunnel HTTPS clients open; allowed hosts get a
  ``200`` and a raw bidirectional pipe, others a ``403``.
- an absolute-form request line (``GET http://host/path HTTP/1.1``) — plain
  HTTP through a proxy; forwarded verbatim to the upstream host if allowed.

Anything else gets ``400``. There is no caching, no TLS interception, no
rewriting — a deliberately small surface.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass

EventHook = Callable[[dict], None] | Callable[[dict], Awaitable[None]] | None

_BUF = 64 * 1024


def host_allowed(host: str, allowlist: Sequence[str]) -> bool:
    """True iff `host` equals an allowlist entry or is a sub-domain of one.

    Entries are compared case-insensitively; a leading dot is ignored
    (``.example.com`` and ``example.com`` both match ``example.com`` and
    ``api.example.com``). An empty allowlist denies everything.
    """
    h = host.strip().lower().rstrip(".")
    if not h:
        return False
    for raw in allowlist:
        entry = raw.strip().lower().lstrip(".").rstrip(".")
        if not entry:
            continue
        if h == entry or h.endswith("." + entry):
            return True
    return False


@dataclass
class _Decision:
    allowed: bool
    host: str
    port: int
    method: str


class AllowlistEgressProxy:
    def __init__(
        self,
        allowlist: Iterable[str],
        *,
        bind_host: str = "127.0.0.1",
        bind_port: int = 0,
        on_event: EventHook = None,
        connect_timeout: float = 10.0,
    ) -> None:
        self._allowlist = [a for a in allowlist if a and a.strip()]
        self._bind_host = bind_host
        self._bind_port = bind_port
        self._on_event = on_event
        self._connect_timeout = connect_timeout
        self._server: asyncio.AbstractServer | None = None
        self.host: str = bind_host
        self.port: int = bind_port

    # -- lifecycle --------------------------------------------------

    async def start(self) -> tuple[str, int]:
        self._server = await asyncio.start_server(
            self._handle_client, self._bind_host, self._bind_port
        )
        sock = self._server.sockets[0]
        self.host, self.port = sock.getsockname()[0], sock.getsockname()[1]
        return self.host, self.port

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None

    @property
    def endpoint(self) -> str:
        """The ``http://host:port`` a container uses as its ``HTTP_PROXY``."""
        return f"http://{self.host}:{self.port}"

    # -- request handling ------------------------------------------

    async def _emit(self, decision: _Decision) -> None:
        if self._on_event is None:
            return
        payload = {
            "type": "egress_allow" if decision.allowed else "egress_deny",
            "host": decision.host,
            "port": decision.port,
            "method": decision.method,
        }
        try:
            res = self._on_event(payload)
            if asyncio.iscoroutine(res):
                await res
        except Exception:  # noqa: BLE001, S110 - logging must never break a connection
            pass

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            request_line = await reader.readline()
            if not request_line:
                return
            try:
                method, target, _version = request_line.decode(
                    "latin-1"
                ).strip().split(" ", 2)
            except ValueError:
                await _respond(writer, 400, "Bad Request")
                return

            # Consume (and keep) headers up to the blank line.
            headers: list[bytes] = []
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break
                headers.append(line)

            if method.upper() == "CONNECT":
                await self._do_connect(target, reader, writer)
            elif "://" in target:
                await self._do_absolute(method, target, headers, reader, writer)
            else:
                await _respond(writer, 400, "Proxy requests only")
        except (ConnectionResetError, asyncio.IncompleteReadError, BrokenPipeError):
            pass
        finally:
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()

    async def _do_connect(
        self,
        target: str,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        host, _, port_s = target.partition(":")
        port = int(port_s or 443)
        allowed = host_allowed(host, self._allowlist)
        await self._emit(_Decision(allowed, host, port, "CONNECT"))
        if not allowed:
            await _respond(client_writer, 403, f"Host {host!r} not on egress allowlist")
            return
        try:
            upstream_reader, upstream_writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), self._connect_timeout
            )
        except (OSError, asyncio.TimeoutError):
            await _respond(client_writer, 502, "Upstream connect failed")
            return
        client_writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await client_writer.drain()
        await _pipe(client_reader, client_writer, upstream_reader, upstream_writer)

    async def _do_absolute(
        self,
        method: str,
        target: str,
        headers: list[bytes],
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        scheme, _, rest = target.partition("://")
        authority, _, path = rest.partition("/")
        host, _, port_s = authority.partition(":")
        port = int(port_s or (443 if scheme == "https" else 80))
        allowed = host_allowed(host, self._allowlist)
        await self._emit(_Decision(allowed, host, port, method.upper()))
        if not allowed:
            await _respond(client_writer, 403, f"Host {host!r} not on egress allowlist")
            return
        try:
            upstream_reader, upstream_writer = await asyncio.wait_for(
                asyncio.open_connection(
                    host, port, ssl=(scheme == "https")
                ),
                self._connect_timeout,
            )
        except (OSError, asyncio.TimeoutError):
            await _respond(client_writer, 502, "Upstream connect failed")
            return
        # Re-issue in origin form ("GET /path HTTP/1.1").
        upstream_writer.write(
            f"{method} /{path} HTTP/1.1\r\n".encode("latin-1")
            + b"".join(headers)
            + b"\r\n"
        )
        await upstream_writer.drain()
        await _pipe(client_reader, client_writer, upstream_reader, upstream_writer)


async def _respond(writer: asyncio.StreamWriter, code: int, reason: str) -> None:
    body = reason.encode("utf-8")
    writer.write(
        f"HTTP/1.1 {code} {reason}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Content-Type: text/plain\r\n"
        "Connection: close\r\n\r\n".encode("latin-1")
        + body
    )
    with contextlib.suppress(Exception):
        await writer.drain()


async def _pipe(
    a_reader: asyncio.StreamReader,
    a_writer: asyncio.StreamWriter,
    b_reader: asyncio.StreamReader,
    b_writer: asyncio.StreamWriter,
) -> None:
    async def _one(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
        try:
            while True:
                chunk = await src.read(_BUF)
                if not chunk:
                    break
                dst.write(chunk)
                await dst.drain()
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass
        finally:
            with contextlib.suppress(Exception):
                dst.close()

    await asyncio.gather(
        _one(a_reader, b_writer), _one(b_reader, a_writer), return_exceptions=True
    )


@contextlib.asynccontextmanager
async def serve_egress_proxy(
    allowlist: Iterable[str],
    *,
    bind_host: str = "127.0.0.1",
    bind_port: int = 0,
    on_event: EventHook = None,
):
    """Run an `AllowlistEgressProxy` for the duration of the `async with` block,
    yielding the started proxy (`.endpoint` is the ``HTTP_PROXY`` value to hand
    the container)."""
    proxy = AllowlistEgressProxy(
        allowlist, bind_host=bind_host, bind_port=bind_port, on_event=on_event
    )
    await proxy.start()
    try:
        yield proxy
    finally:
        await proxy.stop()
