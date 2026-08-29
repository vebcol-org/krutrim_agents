"""`ResearchReplyCleanupMiddleware` — keeps the `core` prompt's control
contract (`**decision:** ...`) out of the user-facing research reply, leaving
only the `<output_format>` markdown."""

from __future__ import annotations

from krutrim_agents.profiles.research.reply_cleanup import (
    ResearchReplyCleanupMiddleware,
    _clean,
)
from langchain_core.messages import AIMessage, HumanMessage

FINISH_LEAK = """**decision:** finish
**reason:** single-turn answer, no tools needed.
**user_message:** null
**research_instruction:** null

---

<!-- sec:id=S1 level=2 title="Overview" -->
## 1. Overview

Body text with a table.

| a | b |
|---|---|
| 1 | 2 |

<!-- /sec:id=S1 -->"""


def test_clean_strips_finish_contract_keeps_report_body():
    out = _clean(FINISH_LEAK)
    assert out is not None
    assert "**decision:**" not in out and "**reason:**" not in out
    assert out.startswith("<!-- sec:id=S1")
    assert "| a | b |" in out


def test_clean_finish_with_heading_immediately_after_contract():
    out = _clean(
        "**decision:** finish\n**reason:** done\n**user_message:** null\n"
        "**research_instruction:** null\n## 1. Title\n\nBody."
    )
    assert out == "## 1. Title\n\nBody."


def test_clean_colon_outside_asterisks_variant():
    out = _clean(
        "**decision**: continue\n**reason**: proceed\n**user_message**: null\n"
        "**research_instruction**: keep going\n\n# Report\n\nBody."
    )
    assert out == "# Report\n\nBody."


def test_clean_ask_clarification_returns_only_user_message():
    out = _clean(
        "**decision:** ask_clarification\n"
        "**reason:** the entity is ambiguous.\n"
        "**user_message:** Which Mercury do you mean — the planet or the company?\n"
        "**research_instruction:** null"
    )
    assert out == "Which Mercury do you mean — the planet or the company?"


def test_clean_leaves_a_plain_report_untouched():
    plain = "## Findings\n\nText.\n\n| x | y |\n|---|---|\n| 1 | 2 |"
    assert _clean(plain) is None


def test_clean_ignores_a_contract_like_phrase_deep_in_the_body():
    body = "Intro paragraph. " * 40 + "\n**decision:** finish\n\ntail"
    assert _clean(body) is None


def _last(state):
    return state["messages"][-1]


def test_middleware_rewrites_terminal_ai_message_in_place():
    mw = ResearchReplyCleanupMiddleware()
    original = AIMessage(content=FINISH_LEAK, id="ai-1")
    state = {"messages": [HumanMessage(content="brief me"), original]}

    update = mw.after_model(state, runtime=None)

    assert update is not None
    new_last = update["messages"][-1]
    assert new_last.id == "ai-1"  # same id -> replaces, not appends
    assert new_last.content.startswith("<!-- sec:id=S1")
    assert len(update["messages"]) == 2


def test_middleware_noop_when_last_message_has_tool_calls():
    mw = ResearchReplyCleanupMiddleware()
    tool_turn = AIMessage(
        content="**decision:** continue\n**reason:** search first\n"
        "**user_message:** null\n**research_instruction:** look it up",
        id="ai-2",
        tool_calls=[{"name": "web_search", "args": {"query": "x"}, "id": "c1"}],
    )
    state = {"messages": [HumanMessage(content="hi"), tool_turn]}
    assert mw.after_model(state, runtime=None) is None


def test_middleware_noop_on_plain_report():
    mw = ResearchReplyCleanupMiddleware()
    state = {
        "messages": [
            HumanMessage(content="hi"),
            AIMessage(content="## Report\n\nAll good.", id="ai-3"),
        ]
    }
    assert mw.after_model(state, runtime=None) is None


async def test_middleware_async_hook_matches_sync():
    mw = ResearchReplyCleanupMiddleware()
    state = {"messages": [HumanMessage(content="q"), AIMessage(content=FINISH_LEAK, id="a")]}
    update = await mw.aafter_model(state, runtime=None)
    assert update["messages"][-1].content.startswith("<!-- sec:id=S1")
