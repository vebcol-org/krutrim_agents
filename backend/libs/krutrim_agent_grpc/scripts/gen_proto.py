"""Regenerate the committed gRPC stubs from `agent_runtime.proto`.

The generated `*_pb2.py` / `*_pb2_grpc.py` / `*_pb2.pyi` are committed so the
host process and the sandbox image both import them without needing
`grpcio-tools` at runtime (only this script and the image build do).

    uv run --extra codegen python backend/libs/krutrim_agent_grpc/scripts/gen_proto.py

`grpc_tools.protoc` emits a bare `import agent_runtime_pb2` in the generated
`_pb2_grpc.py`; this script rewrites it to a package-relative `from . import ...`
so the stubs import cleanly as `krutrim_agent_grpc.proto.*`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROTO_DIR = Path(__file__).resolve().parents[1] / "src" / "krutrim_agent_grpc" / "proto"
PROTO_FILE = PROTO_DIR / "agent_runtime.proto"


def _fix_relative_imports() -> None:
    grpc_stub = PROTO_DIR / "agent_runtime_pb2_grpc.py"
    text = grpc_stub.read_text()
    fixed = text.replace(
        "\nimport agent_runtime_pb2 as agent__runtime__pb2",
        "\nfrom . import agent_runtime_pb2 as agent__runtime__pb2",
    )
    if fixed != text:
        grpc_stub.write_text(fixed)


def main() -> int:
    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{PROTO_DIR}",
        f"--python_out={PROTO_DIR}",
        f"--grpc_python_out={PROTO_DIR}",
        f"--pyi_out={PROTO_DIR}",
        str(PROTO_FILE),
    ]
    print(" ".join(cmd))
    rc = subprocess.call(cmd)
    if rc == 0:
        _fix_relative_imports()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
