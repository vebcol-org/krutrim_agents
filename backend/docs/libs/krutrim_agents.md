# `krutrim_agents` (backend/libs/krutrim_agents)

Package name: **`krutrim-agents`** (`backend/libs/krutrim_agents/pyproject.toml`). Agent profile **content** only — prompts, roles, and tool wiring per agent type (research/trading/sales, plus the `experiment` test profile). No lifecycle/discovery/graph-assembly logic lives here; that's the engine, [`krutrim_agents_core`](krutrim_agents_core.md), which every profile module below imports from.

```
krutrim_agents/
└── profiles/
    ├── research/
    │   ├── __init__.py         4 roles: main, researcher, critic, writer — see "The research profile" below
    │   ├── agent.py              create_research_agent — hand-rolled ReAct graph, wired via graph_pattern
    │   └── prompts.py             render_system_prompt — PromptRegistry composition, called fresh per turn
    ├── trading/__init__.py     same 4 roles, trading-flavored prompts/models — standard deepagents ReAct (no graph_pattern)
    ├── sales/__init__.py       3 roles only: main, researcher, writer (no critic — proves roles aren't fixed)
    └── experiment/__init__.py  1 role — minimal AG-UI streaming test profile, not a real agent type
```

## Profiles

Each profile module follows the same pattern: import `AgentProfile`/`RoleDefaults`, `register_profile`, the shared tools, `load_prompt`, `build_chat_model` — all from `krutrim_agents_core` — define `KEY`, a `_tools()` factory, a `_subagents(store)` factory; call `register_profile(AgentProfile(...))` at **module import time**. Being imported (by `krutrim_agents_core.registry`'s `pkgutil` scan of `krutrim_agents.profiles`) is what registers a profile — nothing else triggers it. `research` follows this same shape but also sets `graph_pattern` and builds its `main_system_prompt` differently — see its own section below rather than the table, since it's the one profile that diverges structurally.

| Profile | Roles | Tools | Notes |
|---|---|---|---|
| `research` ([`profiles/research/__init__.py`](../../libs/krutrim_agents/src/krutrim_agents/profiles/research/__init__.py)) | `main`, `researcher`, `critic`, `writer` | `web_search`, `fetch_url`, `rag_tool` on main | The reference profile — see [below](#the-research-profile) for its (structurally different) prompt composition and graph. `researcher` gathers/verifies facts, `critic` reviews the draft for unsupported claims/gaps, `writer` produces the final structured report per the markdown export spec. |
| `trading` ([`profiles/trading/__init__.py`](../../libs/krutrim_agents/src/krutrim_agents/profiles/trading/__init__.py)) | same 4 roles | `web_search`, `fetch_url` | Structurally identical to `research`'s *old* shape (static `main_system_prompt=load_prompt(...)`, no `graph_pattern`, standard deepagents ReAct loop) — differs only in prompt wording (tickers/filings/trade-idea framing) and `skills_sources=["/skills/common/", "/skills/trading/"]`. |
| `sales` ([`profiles/sales/__init__.py`](../../libs/krutrim_agents/src/krutrim_agents/profiles/sales/__init__.py)) | `main`, `researcher`, `writer` — **no `critic`** | `web_search`, `fetch_url` | Deliberately proves a profile can shape its own role set — `researcher` looks up a prospect, `writer` drafts outreach. |
| `experiment` ([`profiles/experiment/__init__.py`](../../libs/krutrim_agents/src/krutrim_agents/profiles/experiment/__init__.py)) | `main` only | `web_search`, `fetch_url` | Not a real agent type — exercises the AG-UI streaming path end-to-end, the smallest registered profile. |

Default models are set per role in each profile's `default_models` (e.g. research's `main` defaults to OpenRouter `deepseek/deepseek-v4-flash-0731`, `researcher` to `openai/gpt-4.1-mini`, `critic` to Ollama `llama3.1`) — see the source files for exact values, and remember `ProviderStore` seeds from these but never overwrites a user's saved settings on restart.

## The `research` profile

Unlike every other profile, `research` overrides `AgentProfile.graph_pattern` and builds its system prompt dynamically per turn rather than as a static string. Three files, not one:

- [`__init__.py`](../../libs/krutrim_agents/src/krutrim_agents/profiles/research/__init__.py) — the `AgentProfile` registration, plus the `_graph_pattern`/`_make_system_prompt_fn` glue described below.
- [`agent.py`](../../libs/krutrim_agents/src/krutrim_agents/profiles/research/agent.py) — `create_research_agent`, the hand-rolled ReAct graph builder. See [its design doc](krutrim_agents_core_react_agent.md) (relocated here from `krutrim_agents_core/react_agent.py`, and now actually wired in, not a dormant reference).
- [`prompts.py`](../../libs/krutrim_agents/src/krutrim_agents/profiles/research/prompts.py) — `render_system_prompt`, the `promptstore.PromptRegistry` composition described below.

### Prompt composition — `promptstore.PromptRegistry`, not `load_prompt`

`harness/prompts/research/` holds two kinds of content, loaded two different ways:

- **`system/` subdirectory** — 9 files managed by `PromptRegistry` (`prompts.py`'s module-level `registry = PromptRegistry(settings.prompts_dir("research") / "system")`). Kept in a subdirectory of its own because `PromptRegistry.load_directory` recursively parses *every* `.md` file under the directory it's given and requires each one to have a `<!-- name: ...\n... -->` metadata header — mixing in the plain-text subagent prompts below (no such header) would break loading.
  - `research-agent-main.md` (`name: research_main`) — the composition root. `variables: [core, control_flow, clarification, rag_protocol, tools_use, topology]`; body is just those six placeholders concatenated.
  - `research-agent-system-prompt.md` (`name: core`) — the actual research philosophy/depth-requirements/decision-framework content; the only fragment with real runtime variables (`user_request`, `conversation_context`, `research_state`, `known_information`, `unknown_information`, `available_tools`).
  - `research-agent-control-flow-prompt.md` (`name: control_flow`), `research-agent-clarification-prompt.md` (`name: clarification`), `research-agent-rag-prompt.md` (`name: rag_protocol`), `research-agent-tools-use-prompt.md` (`name: tools_use`) — always-on fragments, no variables of their own.
  - Three **topology variants**, all registered under the same `name: topology` but different `scope`s — `promptstore`'s mechanism for "several variants of the same named prompt", selected at render time via `scopes={"topology": ...}`: `research-agent-react-agent-system-prompt.md` (`scope: react_agent`), `research-agent-planner-execution-prompt.md` (`scope: planner_executor`), `research-agent-swarm-agent-prompt.md` (`scope: swarm_agent`, the one actually used — see below).
- **Plain files directly under `harness/prompts/research/`** — `researcher.md`/`critic.md`/`writer.md`, loaded the ordinary way via `krutrim_agents_core.harness.prompts.load_prompt("research", ...)` for the three `SubAgent`s, exactly like every other profile's subagent prompts. No frontmatter — `load_prompt` just reads the raw file text.

`render_with_children` (not `{include:...}`) is the composition call — it renders each child fragment in isolation and substitutes the *rendered result* into the parent as one plain variable, rather than merging every fragment's variables into one shared namespace. That isolation matters here specifically because `core` alone needs six real variables no other fragment declares. One real gotcha hit while wiring this: `promptstore`'s f-string renderer uses `str.format_map`, so any literal `{`/`}` in a fragment's body (two of the topology-prompt fragments had Python-dict-literal pseudocode, e.g. `findings = {}`) either breaks the render outright or trips a security check that forbids passing a value containing a raw curly brace through a *nested* render — the fix was rewording the pseudocode to avoid literal braces entirely (`dict()` instead of `{}`), not escaping them.

`render_system_prompt(*, user_request, conversation_context, research_state, known_information, unknown_information, available_tools, topology="swarm_agent")` returns the composed prompt with two things appended (plain Python string concatenation, not through `PromptRegistry` — see below for why): a `<scratchpad_protocol>` block telling the agent which three files to keep updated (next section), and an `<output_format>` block containing the **full raw text** of [`markdown-spec.md`](../../harness/prompts/format/markdown/markdown-spec.md) — an LLM can't read a file reference, so the actual spec content has to be in the prompt, not a pointer to it. Both are outside `PromptRegistry` because they're not templated content (no variables, no fragment reuse) — just fixed text loaded/concatenated directly. `markdown-spec.md`'s own content is cached via `@cache` on read (it's static per-process, same as `load_prompt`'s caching).

### Dynamic per-turn rendering — `system_prompt_fn`

`render_system_prompt`'s six variables describe *live loop state*, not something fixed at profile-registration time — so `AgentProfile.main_system_prompt` (a plain `str` field) only ever holds a short static placeholder string; it's never actually sent to the model. The real prompt is built by `research/__init__.py`'s `_make_system_prompt_fn(context)`, a closure passed as `create_research_agent`'s `system_prompt_fn` param (see [the design doc](krutrim_agents_core_react_agent.md#parameters)) — re-invoked with the graph's working `state` on *every* model-node call, not once:

- `user_request` — the first `HumanMessage` found in `state["messages"]`.
- `conversation_context` — a plain deterministic summary of the last 8 messages (no extra LLM call).
- `research_state` / `known_information` / `unknown_information` — read back via `backend.read(path)` from three scratchpad files the agent is instructed (via the `<scratchpad_protocol>` block above) to maintain itself, using its own ordinary filesystem tools: `/workspace/.research/state.md`, `/workspace/.research/known.md`, `/workspace/.research/unknown.md`. A missing file (nothing written yet) falls back to a placeholder string, never an error — a research run early in its lifecycle is a normal state.
- `available_tools` — `f"- {tool.name}: {tool.description}"` per tool in `context.tools` (the profile's explicit tools; middleware-contributed tools like `task` aren't listed here — the `tools_use` fragment documents those generically).

### Graph wiring — `graph_pattern` + swarm topology

`research/__init__.py`'s `_graph_pattern(context)` calls `agent.create_research_agent(model=context.model, tools=context.tools, system_prompt_fn=_make_system_prompt_fn(context), middleware=context.middleware, subagents=context.subagents, ...)` and is set as `AgentProfile(..., graph_pattern=_graph_pattern)` — this is what makes `build_agent()` actually use `create_research_agent` instead of falling through to `context.react_agent()` (plain `deepagents.create_deep_agent`).

`topology="swarm_agent"` is the fixed default (not user-selectable today). Chosen because the swarm-topology prompt's Orchestrator/Search/Analysis/Critic roles map directly onto the `researcher`/`critic`/`writer` `SubAgent`s already wired in `_subagents()`, and `create_research_agent`'s `SubAgentMiddleware` already gives the main loop a `task` tool to delegate to them — selecting `swarm_agent` needed zero new graph code, just which prompt fragment renders into the `{topology}` slot.

### `rag_tool`

Added to `_tools()` alongside `web_search`/`fetch_url` — see [`krutrim_agent_rag.md`](krutrim_agent_rag.md#tool) for what it does and how it resolves the current session id without needing `AgentProfile.tools_factory`'s signature to change.

## Adding a new agent type

Create `krutrim_agents/profiles/<key>/__init__.py` (see `sales` as the simplest full template, or `experiment` as the minimal one), add `backend/harness/{skills,prompts,memory}/<key>/` content, optionally add `libs/agent-renderers/src/<key>/renderer.tsx` (frontend — see [`docs/frontend/agent-renderers.md`](../../docs/frontend/agent-renderers.md)). **No core (`krutrim_agents_core`) file is edited** — the plugin surface this package sits on top of.

## Dependencies

[`pyproject.toml`](../../libs/krutrim_agents/pyproject.toml) — package `krutrim-agents`: `deepagents` (for the `SubAgent` type used in `_subagents()` factories), `promptstore` (the `research` profile's prompt composition — see above), plus the internal workspace deps `krutrim-agents-core` (brings in everything a profile actually needs at runtime: `AgentProfile`, `register_profile`, `load_prompt`, `build_chat_model`, `web_search`, `fetch_url`) and `krutrim-agent-rag` (`rag_tool`, used by `research`).

See [`krutrim_agents_core.md`](krutrim_agents_core.md) for the engine this package plugs into: graph assembly, discovery, provider abstraction, cross-agent messaging, and harness loaders.
