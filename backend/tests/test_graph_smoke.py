from __future__ import annotations

from deepagents.backends.filesystem import FilesystemBackend
from krutrim_agents_core.builder import build_agent
from krutrim_agents_core.harness.readonly_backend import ReadOnlyFilesystemBackend
from krutrim_agents_core.providers.resolver import resolve_models
from krutrim_agents_core.registry import all_profiles
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver


@tool
def _dummy_extra_tool(x: str) -> str:
    """A dummy tool used only to prove extra_tools reaches the compiled graph."""
    return x


def _fs_backend(tmp_path) -> FilesystemBackend:
    return FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)


def test_every_registered_profile_compiles(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    for key, profile in all_profiles().items():
        graph = build_agent(profile, resolve_models(profile), _fs_backend(tmp_path))
        assert graph.name == key


def test_build_agent_defaults_to_in_memory_checkpointer(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    _key, profile = next(iter(all_profiles().items()))

    graph = build_agent(profile, resolve_models(profile), _fs_backend(tmp_path))

    assert isinstance(graph.checkpointer, InMemorySaver)


def test_build_agent_uses_injected_checkpointer(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    _key, profile = next(iter(all_profiles().items()))
    saver = InMemorySaver()

    graph = build_agent(
        profile, resolve_models(profile), _fs_backend(tmp_path), checkpointer=saver
    )

    assert graph.checkpointer is saver


def test_build_agent_includes_extra_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    _key, profile = next(iter(all_profiles().items()))

    without = build_agent(profile, resolve_models(profile), _fs_backend(tmp_path))
    with_extra = build_agent(
        profile,
        resolve_models(profile),
        _fs_backend(tmp_path),
        extra_tools=[_dummy_extra_tool],
    )

    assert "_dummy_extra_tool" not in without.nodes["tools"].bound.tools_by_name
    assert "_dummy_extra_tool" in with_extra.nodes["tools"].bound.tools_by_name


def test_readonly_backend_denies_writes(tmp_path):
    (tmp_path / "note.md").write_text("original", encoding="utf-8")
    backend = ReadOnlyFilesystemBackend(root_dir=tmp_path, virtual_mode=True)

    read_result = backend.read("/note.md")
    assert read_result.file_data["content"] == "original"

    write_result = backend.write("/note.md", "hacked")
    assert write_result.error is not None
    assert (tmp_path / "note.md").read_text(encoding="utf-8") == "original"

    edit_result = backend.edit("/note.md", "original", "hacked")
    assert edit_result.error is not None

    delete_result = backend.delete("/note.md")
    assert delete_result.error is not None
    assert (tmp_path / "note.md").exists()
