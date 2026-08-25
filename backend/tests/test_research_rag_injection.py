from __future__ import annotations

from types import SimpleNamespace

from krutrim_agent_management.config import settings
from krutrim_agent_rag.middleware import RagInjectionMiddleware
from krutrim_agents.profiles import research as research_profile


def _fake_context() -> SimpleNamespace:
    return SimpleNamespace(
        model=object(),
        tools=[],
        middleware=[],
        subagents=[],
        skills=[],
        memory=None,
        backend=SimpleNamespace(),
        checkpointer=None,
        name="research",
    )


def _capture_middleware(monkeypatch) -> dict:
    captured: dict = {}

    def fake_create_research_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(research_profile, "create_research_agent", fake_create_research_agent)
    return captured


def test_graph_pattern_excludes_rag_injection_middleware_by_default(monkeypatch):
    monkeypatch.setattr(settings, "rag_injection_enabled", False)
    captured = _capture_middleware(monkeypatch)

    research_profile._graph_pattern(_fake_context())

    assert not any(isinstance(m, RagInjectionMiddleware) for m in captured["middleware"])


def test_graph_pattern_includes_rag_injection_middleware_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "rag_injection_enabled", True)
    captured = _capture_middleware(monkeypatch)

    research_profile._graph_pattern(_fake_context())

    assert any(isinstance(m, RagInjectionMiddleware) for m in captured["middleware"])


def test_graph_pattern_does_not_mutate_context_middleware(monkeypatch):
    """Other profiles share `context.middleware`'s underlying list via
    `build_agent()` — `_graph_pattern` must build its own list, not append
    in place."""
    monkeypatch.setattr(settings, "rag_injection_enabled", True)
    _capture_middleware(monkeypatch)
    context = _fake_context()
    original_middleware = context.middleware

    research_profile._graph_pattern(context)

    assert original_middleware == []
