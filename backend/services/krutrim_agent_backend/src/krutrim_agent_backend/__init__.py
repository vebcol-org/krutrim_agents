def main() -> None:
    """`uv run krutrim-agent-backend` — starts the FastAPI/uvicorn server."""
    import uvicorn
    from krutrim_agent_management.config import settings

    uvicorn.run(
        "krutrim_agent_backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
