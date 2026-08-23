"""Agent profile content — one subpackage per agent type under `krutrim_agents.profiles`.

This package holds only plugin *content* (prompts, roles, tool wiring per
agent type) — no lifecycle/discovery/graph-assembly logic. That engine lives
in `krutrim_agents_core` (see `krutrim_agents_core.registry`, `krutrim_agents_core.builder`), which
this package's profile modules import from, never the other way around.
"""
