"""Keep the research agent's *control contract* out of its user-facing reply.

`core`'s "Output Contract" asks the model to emit a structured interaction
decision (`**decision:** / **reason:** / **user_message:** / **research_instruction:**`)
before it does anything user-facing. In an orchestrated topology a supervisor
would consume that block and route on it; the single-agent ReAct compile in
`agent.create_research_agent` has no such consumer, so without this the model's
raw decision block is prepended to every final answer and shipped to the user
verbatim (observed with smaller models).

This middleware runs on the terminal turn only (the last AI message, no pending
tool calls) and rewrites that message:

- `decision: finish` / `continue`  -> drop the contract block, keep the report
  body that follows it (this is the markdown that must satisfy `<output_format>`).
- `decision: ask_clarification` / `request_approval` / `request_choice`
  -> replace the whole message with the `user_message` value, which is exactly
  what those decisions are meant to surface.
- anything it can't parse confidently -> left untouched.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

# Matches the field label in any of the shapes models actually emit:
# ``**decision:**``, ``**decision**:``, ``**decision** ``, ``decision:``.
_FIELD_RE = re.compile(
    r"(?:^|\n)[ \t]*\**(decision|reason|user_message|research_instruction)"
    r"\**[ \t]*:?\**[ \t]*",
    re.IGNORECASE,
)
_FINISH = {"finish", "continue"}
_INTERACT = {"ask_clarification", "request_approval", "request_choice"}


def _clean(content: str) -> str | None:
    """Return the cleaned message text, or ``None`` to leave it unchanged."""
    head = content.lstrip()
    first = _FIELD_RE.search(head)
    # Only engage when the contract is actually at the top of the reply.
    if not first or first.start() > 400:
        return None

    # Find every contract field label, in order.
    order = [(m.start(), m.end(), m.group(1).lower()) for m in _FIELD_RE.finditer(head)]
    if not any(name == "decision" for _, _, name in order):
        return None

    # The contract block ends at the first blank line / horizontal rule /
    # heading after the LAST field label — that's where the report body starts.
    last_label_end = order[-1][1]
    tail = head[last_label_end:]
    sep = re.search(r"\n[ \t]*\n|\n[ \t]*(?:-{3,}|\*{3,})[ \t]*\n|\n[ \t]*#", tail)
    block_end = last_label_end + (sep.start() if sep else len(tail))

    fields: dict[str, str] = {}
    for idx, (_start, end, name) in enumerate(order):
        value_end = order[idx + 1][0] if idx + 1 < len(order) else block_end
        fields[name] = head[end:value_end].strip()

    decision_tokens = fields.get("decision", "").strip().strip("`").lower().split()
    decision = decision_tokens[0] if decision_tokens else ""

    # Drop a lone "---" / "***" rule the model tends to put between the
    # contract and the report.
    body = re.sub(r"^\s*(?:-{3,}|\*{3,})\s*\n", "", head[block_end:].lstrip(), count=1)
    body = body.strip()

    if decision in _INTERACT:
        msg = fields.get("user_message", "").strip().strip("`")
        if msg and msg.lower() != "null":
            return msg
        return body or None
    if decision in _FINISH:
        return body or None
    return None


class ResearchReplyCleanupMiddleware(AgentMiddleware):
    @property
    def name(self) -> str:
        return "ResearchReplyCleanupMiddleware"

    def _rewrite(self, state: dict[str, Any]) -> dict[str, Any] | None:
        messages = state.get("messages") or []
        if not messages:
            return None
        last = messages[-1]
        if not isinstance(last, AIMessage) or (getattr(last, "tool_calls", None) or []):
            return None
        content = last.content
        if not isinstance(content, str) or not content.strip():
            return None
        cleaned = _clean(content)
        if cleaned is None or cleaned == content:
            return None
        return {
            "messages": [
                *messages[:-1],
                AIMessage(content=cleaned, id=last.id),
            ]
        }

    def after_model(
        self, state: dict[str, Any], runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        return self._rewrite(state)

    async def aafter_model(
        self, state: dict[str, Any], runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        return self._rewrite(state)
