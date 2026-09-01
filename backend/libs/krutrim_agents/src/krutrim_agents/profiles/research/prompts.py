"""Composes the research agent's system prompt from the modular fragments
under `harness/prompts/research/` via `promptstore.PromptRegistry`.

The registry holds six always-on fragments (`core`, `control_flow`,
`clarification`, `rag_protocol`, `tools_use`) plus one selectable topology
variant (`topology`, registered three times under different `scope`s:
`react_agent` / `planner_executor` / `swarm_agent`). `render_with_children`
renders each fragment in isolation and substitutes the result into the
`research_main` parent prompt — this keeps `core`'s six runtime variables
from colliding with any other fragment's namespace, which a flat
`{include:...}` merge would not.

`render_system_prompt` is called fresh on every model-node invocation (see
`research/agent.py`'s `system_prompt_fn`), not once at profile-registration
time, since the core prompt's Runtime Context block is designed to reflect
the research loop's live state.
"""

from __future__ import annotations

from functools import cache

from krutrim_agent_management.config import settings
from promptstore import PromptRegistry

PROMPT_DIR = settings.prompts_dir("research") / "system"
"""Only the composable PromptRegistry-managed fragments live here — kept
separate from the plain `load_prompt`-style subagent prompts (`researcher.md`
etc.) directly under `prompts_dir("research")`, since `PromptRegistry`
recursively parses every `.md` under its directory and would otherwise choke
on files with no `<!-- ... -->` metadata header."""

registry = PromptRegistry(PROMPT_DIR)

_FORMAT_SPEC_PATH = (
    settings.prompts_root_dir / "format" / "markdown" / "markdown-spec.md"
)


@cache
def _load_format_spec() -> str:
    return _FORMAT_SPEC_PATH.read_text(encoding="utf-8").strip()


# `promptstore`'s PromptRegistry rejects any *rendered value* that still contains
# a raw `{` / `}` (a template-injection guard). Every variable we feed `core` is
# dynamic free text — a conversation summary that quotes tool-call JSON, the
# agent's own markdown scratchpads, tool descriptions — so "no braces" can't be
# assumed. Swap them for full-width look-alikes: accepted by the registry, still
# perfectly legible to the model.
_BRACE_SUBS = str.maketrans({"{": "｛", "}": "｝"})


def _sanitize(value: str) -> str:
    return value.translate(_BRACE_SUBS)


def render_system_prompt(
    *,
    user_request: str,
    conversation_context: str,
    research_state: str,
    known_information: str,
    unknown_information: str,
    available_tools: str,
    topology: str = "swarm_agent",
) -> str:
    """Render the full research agent system prompt.

    `topology` selects which alternate execution-topology fragment fills the
    `{topology}` slot: one of `react_agent`, `planner_executor`, `swarm_agent`
    (the three `scope`s the `topology`-named prompt is registered under).
    """
    composed = registry.render_with_children(
        "research_main",
        children={
            "core": {
                "variables": {
                    "user_request": _sanitize(user_request),
                    "conversation_context": _sanitize(conversation_context),
                    "research_state": _sanitize(research_state),
                    "known_information": _sanitize(known_information),
                    "unknown_information": _sanitize(unknown_information),
                    "available_tools": _sanitize(available_tools),
                }
            },
            "control_flow": {},
            "clarification": {},
            "rag_protocol": {},
            "tools_use": {},
            "topology": {},
        },
        scopes={"topology": topology},
    )
    return (
        f"{composed}\n\n"
        f"{_SCRATCHPAD_PROTOCOL}\n\n"
        f"{_FINAL_ANSWER_PROTOCOL}\n\n"
        f"<output_format>\n{_load_format_spec()}\n</output_format>"
    )


# Marker string — kept byte-for-byte in sync with the frontend split in
# `libs/agent-ui/src/utils/render-payload.ts` (`FINAL_REPORT_MARKER`).
_FINAL_ANSWER_PROTOCOL = """\
<final_answer_protocol>
Everything you write reaches the user in two separate places:

1. Your working narration — plans, progress notes, what you are checking and why,
   dead ends — streams into a live activity log as you go. Write it naturally.
2. Your finished deliverable is shown on its own as the report.

Separate the two with a single marker line, written exactly as:

===FINAL_REPORT===

Rules for the marker:
- Emit it once, on its own line, only when the research is done and you are ready
  to hand over the report.
- Everything AFTER the marker is the report and MUST follow <output_format>
  below. It is the only part the user keeps.
- Do not wrap the report in <answer>, <report>, <final_report> or any other tag,
  and do not repeat the marker.
- If you are not ready to deliver yet, do not emit the marker at all.
</final_answer_protocol>"""


_SCRATCHPAD_PROTOCOL = """\
<scratchpad_protocol>
Your Runtime Context above (research_state/known_information/unknown_information) is \
re-read from these files on every turn — it will not update on its own. Keep them \
current using your ordinary filesystem write/edit tools:
- /workspace/.research/state.md — what stage you're in and what you're doing next
- /workspace/.research/known.md — verified findings so far, one per line or section
- /workspace/.research/unknown.md — open questions / unresolved sub-questions

Write to these as soon as your understanding changes, not just at the end — an empty \
or stale file means the next turn's Runtime Context will be empty or stale too.
</scratchpad_protocol>"""
