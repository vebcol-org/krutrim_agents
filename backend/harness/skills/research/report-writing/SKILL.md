---
name: report-writing
description: How to structure a general research report so it renders well in the analysis canvas. Use whenever producing a finished write-up for the user, not just answering a quick factual question.
license: MIT
---

# Report Writing

## When to Use

Use this structure whenever asked to research and report on a topic — not for one-off factual lookups that don't need a document.

## Structure

A complete report is markdown with these sections, in order:

1. **Summary** — one paragraph: what was researched and the headline takeaway.
2. **Findings** — the concrete points the report rests on, each with its source. Group related findings under short subheadings if there are more than a handful.
3. **Analysis** — what the findings mean together. Note where sources agree, where they conflict, and what remains uncertain.
4. **Open Questions / Limitations** — what couldn't be verified, what's out of date, or what would need more research to resolve.
5. **Sources** — a list of everything cited, so the reader can check the work.

## Rules

- Every non-obvious claim needs a source (see the `web-research` skill).
- Don't pad a report to look thorough — a short report with solid sources beats a long one with weak ones.
- State uncertainty plainly rather than picking a side to sound more decisive than the evidence supports.
- Once the report is finalized, call `render_content` with `kind="markdown"` so it shows up in the canvas — don't just leave it in the chat reply.
