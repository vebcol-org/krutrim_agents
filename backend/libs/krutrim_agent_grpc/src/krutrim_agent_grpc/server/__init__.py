"""The in-sandbox AgentRuntime gRPC server.

`python -m krutrim_agent_grpc.server` is the sandbox image's CMD (see
`docker/sandbox.Dockerfile`); it binds `0.0.0.0:50051` and reads its endpoints
from `/run/krutrim_agent/run.json`. It builds and streams the real agent graph
in-process — the container is the sandbox now — and forwards each AG-UI event to
the host over `RunTurn`.
"""
