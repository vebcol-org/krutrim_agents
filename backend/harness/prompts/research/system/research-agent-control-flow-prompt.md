<!--
name: control_flow
version: 1.0.0
render_engine: f-string
description: Deep research control-flow loop — plan/act/observe/reflect, budgets, exit conditions.
-->

You are about to run a multi-step deep research task. Follow this control flow
exactly, in addition to your system-level instructions.

RESEARCH REQUEST:
<insert the actual research question / topic here>

CONFIGURATION:
- max_iterations: <e.g., 8>              # hard cap on plan→act→observe→reflect loops
- max_tool_calls: <e.g., 40>             # hard cap on total tool invocations
- confidence_bar: <High | Medium>         # minimum confidence to accept a finding
  without another verification pass
- depth_mode: <quick | standard | exhaustive>
  - quick: top-level answer with 1 verification pass per major claim
  - standard: full Core Research Prompt coverage, 2 verification passes for
    load-bearing claims
  - exhaustive: full coverage + stakeholder/perspective analysis + explicit
    unresolved-questions section + Critic Agent pass
- allow_clarifying_questions: <true | false>
- rag_available: <true | false>           # if true, RAG Prompt is active

CONTROL LOOP (pseudocode — follow this logic):
```python
plan = generate_subquestions(request) iteration = 0 findings = dict() open_questions = []

while iteration < max_iterations: 
    iteration += 1 
    for sq in plan.unresolved(): 
        if sq.type == "RAG" and rag_available: 
            result = rag_tool(sq.as_question()) 
        elif sq.type == "WEB": 
            result = web_search(sq.as_query()) 
        elif sq.type == "COMPUTE": 
            result = code_execution(sq.as_expression()) 
        elif sq.type == "NEEDS_USER" and allow_clarifying_questions: 
            result = ask_user(sq.as_question()) # pauses loop, one question only else: result = None open_questions.append(sq) 
            continue

    findings[sq] = tag_and_score(result)
    new_subqs = extract_new_subquestions(result)
    plan.extend(new_subqs)

if all_resolved(plan, confidence_bar) or tool_calls_used >= max_tool_calls:
    break

if depth_mode == "exhaustive": findings = critic_pass(findings)

report = synthesize(findings, open_questions, depth_mode) return report
```

EXIT CONDITIONS (stop the loop immediately if any is true):
1. All sub-questions resolved at or above confidence_bar.
2. max_iterations reached.
3. max_tool_calls reached.
4. A hard blocker is hit (tool unavailable, RAG context confirmed empty on a
   critical blocking question, contradiction that cannot be resolved with
   available tools) — in this case, stop and report the blocker, do not keep
   looping hoping it resolves itself.
5. User explicitly says stop / has enough / change direction.

ON EXIT, ALWAYS PRODUCE:
- Final synthesized answer, structured per the Core Research Prompt's Depth
  Requirements.
- A source log separating [RAG] / [WEB] / [COMPUTED] / [INFERENCE].
- An explicit "Open Questions" section for anything not resolved, even if minor.
- If depth_mode == exhaustive: a brief confidence rationale per major claim.

Do not silently exceed the configured budgets. Do not silently drop open questions
from the final report.
