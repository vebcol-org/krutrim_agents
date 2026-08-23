"""Accumulates per-session token usage into `usage.json`."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

_USAGE_FIELDS = ("input_tokens", "output_tokens", "total_tokens")


def accumulate_usage(
    existing: dict[str, Any] | None, reply: AIMessage
) -> dict[str, Any]:
    """Folds one turn's usage (from `reply.usage_metadata`, if the provider reported any) into
    the running totals + per-turn log already stored for this session.
    """
    turn_usage = dict(getattr(reply, "usage_metadata", None) or {})
    totals = dict((existing or {}).get("totals") or {})
    for field in _USAGE_FIELDS:
        totals[field] = totals.get(field, 0) + turn_usage.get(field, 0)

    turns = list((existing or {}).get("turns") or [])
    turns.append({field: turn_usage.get(field, 0) for field in _USAGE_FIELDS})

    return {"totals": totals, "turns": turns}
