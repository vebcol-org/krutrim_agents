# `research/agent.py` — the hand-rolled ReAct graph builder behind the `research` profile

[`agent.py`](../../libs/krutrim_agents/src/krutrim_agents/profiles/research/agent.py) (`create_research_agent`) — a second, independent way to compile a deep agent, alongside [`builder.py`](krutrim_agents_core.md#1-build_agent--the-graph-assembler)'s `build_agent`/`create_deep_agent` path. **This file used to live at `krutrim_agents_core/react_agent.py` as a dormant reference blueprint ("not wired into any live code path"). It has since moved into the `krutrim_agents` content package and renamed `create_deep_agent` → `create_research_agent`, and is now the actual compiled graph the `research` profile runs** — set as its `AgentProfile.graph_pattern` in [`krutrim_agents/profiles/research/__init__.py`](../../libs/krutrim_agents/src/krutrim_agents/profiles/research/__init__.py) (see [`krutrim_agents.md`](krutrim_agents.md#the-research-profile)). The relocation reflects `krutrim_agents_core`'s own dependency rule: core never imports agent *content*, and this file — once it became a specific profile's actual graph, not a generic reference — belonged in the content package instead.

## Why this exists

`deepagents.create_deep_agent` always ends by calling `langchain.agents.create_agent`, which compiles a **fixed** topology: a `model` node, a `tools` node, and conditional edges that can only land on `{"model", "tools", "end"}` (`langchain.agents.middleware.types.JumpTo`). There is no parameter to swap that topology — every middleware hook (`before_model`, `wrap_model_call`, ...) customizes *behavior at* those three nodes, never the graph *shape*. See [`AgentProfile.graph_pattern`](krutrim_agents_core.md#2-agentprofile--roledefaults--the-plugin-contract) for the supported way to plug an alternative top-level topology into `build_agent` while still using the real `deepagents.create_deep_agent` for individual worker nodes.

`research/agent.py` is the other option: skip `deepagents.create_deep_agent`/`langchain.agents.create_agent` entirely and assemble the `StateGraph` by hand, while still reusing deepagents' actual building blocks (backends, `FilesystemMiddleware`, `SubAgentMiddleware`, `SkillsMiddleware`, `MemoryMiddleware`, `DeepAgentState`) instead of reimplementing them. Read this file when you want to understand — or replace — the node/edge wiring itself, not just the behavior inside it.

## What's reused vs. hand-built vs. omitted

| Reused as-is | Hand-built here | Deliberately omitted |
|---|---|---|
| `deepagents.DeepAgentState` (message state + checkpoint-growth reducer) | the `StateGraph`: nodes, edges, conditional routing | `jump_to` / `Command` support (used by e.g. `RubricMiddleware`, not the default stack) |
| `deepagents.backends.*` (`StateBackend`, `CompositeBackend`, ...) | the hook runner: calls `before_agent`/`before_model`/`after_model` on every middleware, in order, merging state updates | `response_format` / structured output |
| `FilesystemMiddleware`, `SubAgentMiddleware`, `SkillsMiddleware`, `MemoryMiddleware`, `PatchToolCallsMiddleware` | the `wrap_model_call` / `wrap_tool_call` composition (first middleware in the list = outermost — same convention `create_agent` documents) | `interrupt_on` / `HumanInTheLoopMiddleware` |
| `langchain.agents.middleware.types.{AgentMiddleware, ModelRequest, ModelResponse, ToolCallRequest, ExtendedModelResponse}` — typed dataclasses / the base class every middleware subclasses, not the `create_agent` factory | the base "call the model" / tool-execution handlers those hooks wrap around | harness profiles (deepagents' per-model prompt/tool-override system) |
| | dynamic per-turn system prompt rendering (`system_prompt_fn`, below) | prompt-caching, summarization, async subagents (see "Extending") |
| | | async graph execution — only sync hooks (`before_model`, not `abefore_model`) are run |

## Graph shape

```
START -> before_agent -> model --(last AIMessage has tool_calls?)--> tools -> model
                             \--(no tool_calls)---------------------------> END
```

Two structural nodes only:

- **`before_agent`** — runs once, before the first model call. Calls every middleware's `before_agent` hook (e.g. `SkillsMiddleware`/`MemoryMiddleware` load their index/content into state here) and merges the returned state updates.
- **`model`** — runs `before_model` hooks, builds a `ModelRequest` (model, messages, system message, tools, state, runtime), runs it through the composed `wrap_model_call` chain, then `after_model` hooks. Returns the new `AIMessage` plus any hook state updates.
- **`tools`** — a plain `langgraph.prebuilt.ToolNode` over every tool the middleware stack + caller contributed, given the composed `wrap_tool_call` chain via `ToolNode(tools, wrap_tool_call=...)`. Present only when there's at least one tool; otherwise `model` routes straight to `END`.

This is the entire "pattern" `create_deep_agent` hardcodes. To build a different one (planner → worker → critic, supervisor routing, reflection loop), replace the `graph.add_node(...)`/`add_edge(...)` calls in `create_research_agent()`'s body — the middleware-stack assembly and hook-running helpers above them don't need to change.

## Parameters

Same names as `deepagents.create_deep_agent`, implemented subset, plus one addition:

| Param | Wired to |
|---|---|
| `model` | passed straight to the model node's `ModelRequest` |
| `tools` | merged with every middleware's `.tools` into `all_tools` |
| `system_prompt` | wrapped in a `SystemMessage`, set as `ModelRequest.system_message` each call (middleware mutate it via `wrap_model_call`, e.g. `FilesystemMiddleware` appends host-path routing info) |
| `system_prompt_fn` | **New.** `Callable[[dict], str] \| None`, takes precedence over `system_prompt` when supplied — re-invoked with the graph's working `state` on *every* model-node call, not once at graph-build time. This is what lets the `research` profile's system prompt reflect live loop state (its Runtime Context block — `research_state`/`known_information`/`unknown_information`) instead of being frozen at `AgentProfile` registration. See [`krutrim_agents.md`](krutrim_agents.md#the-research-profile) for how `research/__init__.py` builds this closure and what scratchpad files it reads back. |
| `middleware` | appended to the base stack (skills → filesystem → subagents → patch-tool-calls → memory → *yours*) |
| `subagents` | `SubAgentMiddleware(backend=backend, subagents=subagents)` → contributes the `task` tool |
| `skills` | `SkillsMiddleware(backend=backend, sources=skills)` |
| `memory` | `MemoryMiddleware(backend=backend, sources=memory)` |
| `permissions` | `FilesystemMiddleware(..., _permissions=permissions)` — enforced via its `wrap_tool_call` hook, chained through `ToolNode` |
| `backend` | shared by every middleware that touches the filesystem; defaults to `StateBackend()` |
| `checkpointer`, `store`, `cache`, `debug`, `name` | passed straight through to `StateGraph.compile(...)` |
| `context_schema` | passed to `StateGraph(...)` |
| `state_schema` | base graph schema; defaults to `DeepAgentState` |

Accepted by real `create_deep_agent` but **not present here** (add them yourself if you need them): `response_format`, `interrupt_on`, `state_schema` merging with per-middleware `state_schema` (this blueprint uses one fixed schema, not deepagents' schema-union logic).

## A real version-skew bug this file hit (and fixed) once it was actually wired in

The hook runner (`_run_state_hooks`) originally called every middleware's `before_agent`/`before_model`/`after_model` hook with just `(state, runtime)` — matching `AgentMiddleware`'s *base* signature. The installed `deepagents` version's `SkillsMiddleware.before_agent`/`MemoryMiddleware.before_agent` actually take a third `config: RunnableConfig` parameter, which this file never supplied — so the moment `research`'s `skills_sources`/`memory_sources` (both always non-empty, unlike this doc's earlier smoke tests which passed `skills=None`/`memory=None`) exercised those middleware for the first time in a real request, it raised `TypeError: SkillsMiddleware.before_agent() missing 1 required positional argument: 'config'`.

Fixed with a small `_hook_accepts_config(mw, hook_name)` helper (`inspect.signature` check) plus `langgraph.config.get_config()` — the hook runner now fetches the ambient `RunnableConfig` and passes it only to hooks that actually declare a `config` parameter, leaving every other hook's call signature unchanged. This is the kind of bug this design doc's "Known gaps found while testing this blueprint" section (below) was written to warn about — a hand-rolled reimplementation of `create_agent`'s internals will drift from whatever the real `create_agent`/middleware classes do internally as `deepagents` itself evolves, and only gets caught once something actually exercises the drifted path end-to-end.

## Known gaps found while testing this blueprint

Verified by hand (fake chat models, no real LLM) during initial development — see the smoke tests run at the time, not checked into `tests/` since this file wasn't wired into any live path yet:

- **model ↔ tools loop**: works — a tool-calling `AIMessage` routes to `tools`, the `ToolMessage` routes back to `model`.
- **`wrap_model_call` composition**: works, and matches `create_agent`'s documented "first middleware in the list = outermost" convention — outer's request mutation happens before inner's, so both land in the final request the base handler sees.
- **`wrap_tool_call` composition / `FilesystemMiddleware` permissions**: works — a `deny` rule on a path correctly short-circuits `write_file` with a permission-denied `ToolMessage`, proven by chaining through `ToolNode(wrap_tool_call=...)`.
- **Subagents need fully-specified specs.** Real `create_deep_agent` (`deepagents/graph.py`) has a whole preprocessing loop that defaults each `SubAgent`'s `model` to the parent's model and its `tools` to the parent's tools when unset, before handing specs to `SubAgentMiddleware`. This blueprint skips that preprocessing — every subagent spec here **must** set its own `model` and `tools` explicitly, or `SubAgentMiddleware` raises `ValueError`. (`research/__init__.py`'s `_subagents()` does set both explicitly for `researcher`/`critic`/`writer`, so this doesn't bite in practice.)
- **`SubAgentMiddleware`'s own `system_prompt` kwarg is left unset**, matching `builder.py`'s actual usage (it isn't passed there either) — the model learns about subagents from the `task` tool's schema description, not a system-prompt injection. If you want the "Available subagent types" system-prompt block deepagents' docs describe, pass `system_prompt=` to the `SubAgentMiddleware(...)` construction in `create_research_agent()`.
- **The `config`-parameter gap above** — found only once this file actually ran with non-empty `skills`/`memory` sources in a real request, i.e. after wiring, not during the original hand-tested smoke pass.

## Extending

- **Different topology**: fork `create_research_agent()`'s body. Keep the middleware-stack assembly (it's what gives you filesystem/subagent/skills/memory tools for free) and change only the `graph.add_node`/`add_edge` calls at the bottom. A compiled sub-graph from this same function is a plain `Runnable` — you can nest one inside another as a node, same as `DeepAgentContext.react_agent()` in `builder.py`.
- **Async**: add `abefore_agent`/`abefore_model`/`aafter_model`/`awrap_model_call`/`awrap_tool_call` variants of the hook runners and use `graph.ainvoke`/`ToolNode`'s `awrap_tool_call`.
- **`jump_to`**: after running `before_model`/`after_model` hooks, check `updates.get("jump_to")` and route directly to `"tools"`/`END` instead of calling the model, mirroring `create_agent`'s handling.
- **Prompt caching / summarization / async subagents**: these are just more `AgentMiddleware` instances (`deepagents.middleware.summarization.create_summarization_middleware(model, backend)`, `deepagents.middleware.async_subagents.AsyncSubAgentMiddleware`, `langchain_anthropic.middleware.AnthropicPromptCachingMiddleware`) — append them to `stack` in `create_research_agent()`, no other change needed since the hook runner already handles arbitrary middleware generically.
- **Wiring a different profile onto this**: give it a `graph_pattern` callable (see [`krutrim_agents_core.md`](krutrim_agents_core.md)) that imports and calls `research.agent.create_research_agent(...)` (or copies this file into its own profile package, if it needs different graph-shape logic, not just different prompts/tools) with `context`'s fields instead of `context.react_agent()`.
