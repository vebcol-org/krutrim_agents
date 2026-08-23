"""Runs `harness/evals/datasets/<agent_key>.jsonl` tasks through that agent
profile and checks each response against simple required-substring assertions.

This is a developer tool, not part of `pytest` — it makes real LLM calls
(needs `OPENROUTER_API_KEY` set, or Ollama running locally for whichever
roles use it) and a running Docker daemon for the sandbox. Run it directly:

    uv run python harness/evals/runner.py <agent_key>   # e.g. research, trading, sales
"""

from __future__ import annotations

import json
import sys

from langchain_core.messages import HumanMessage

from krutrim_agent_management.config import settings
from krutrim_agent_sandbox.docker_backend import DockerSandboxBackend
from krutrim_agent_sandbox.policy import SandboxPolicy
from krutrim_agents_core.builder import build_agent
from krutrim_agents_core.providers.store import ProviderStore
from krutrim_agents_core.registry import get_profile


def load_dataset(agent_key: str) -> list[dict]:
    path = settings.evals_dir / "datasets" / f"{agent_key}.jsonl"
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run_dataset(agent_key: str) -> bool:
    profile = get_profile(agent_key)
    tasks = load_dataset(agent_key)
    store = ProviderStore(settings.provider_settings_path)
    sandbox = DockerSandboxBackend(
        policy=SandboxPolicy(image=settings.sandbox_image), owner_id=agent_key
    )
    all_passed = True
    try:
        graph = build_agent(profile, store, sandbox)
        for task in tasks:
            result = graph.invoke({"messages": [HumanMessage(content=task["prompt"])]})
            final_text = result["messages"][-1].content
            if isinstance(final_text, list):
                final_text = "\n".join(
                    part.get("text", "")
                    for part in final_text
                    if isinstance(part, dict)
                )
            missing = [
                s
                for s in task.get("required_substrings", [])
                if s.lower() not in final_text.lower()
            ]
            passed = not missing
            all_passed &= passed
            status = "PASS" if passed else "FAIL"
            print(f"[{status}] {task['id']}")
            if missing:
                print(f"  missing: {missing}")
            print(f"  --- response ---\n{final_text}\n")
    finally:
        sandbox.close()
    return all_passed


if __name__ == "__main__":
    agent_key = sys.argv[1] if len(sys.argv) > 1 else "research"
    ok = run_dataset(agent_key)
    sys.exit(0 if ok else 1)
