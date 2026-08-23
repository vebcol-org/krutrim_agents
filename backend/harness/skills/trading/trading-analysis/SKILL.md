---
name: trading-analysis
description: How to structure a trading/investment analysis report so it renders well in the analysis canvas. Use whenever producing a final analysis for the user, not just answering a quick question.
license: MIT
---

# Trading Analysis

## When to Use

Use this structure whenever you're asked to analyze a ticker, sector, or trade idea — not for quick factual lookups.

## Structure

A complete analysis is markdown with these sections, in order:

1. **Summary** — one paragraph: what this is, the headline view (e.g. bullish/bearish/neutral, or "no clear edge"), and the confidence level.
2. **Key Facts** — a bulleted or tabular list of the concrete data points the analysis rests on (price, recent performance, relevant fundamentals/technicals), each with its source.
3. **Analysis** — the reasoning: what the facts imply, both the bull case and the bear case. Never present only one side.
4. **Risks** — what would invalidate this view. Be concrete (e.g. "earnings on Nov 3 could move this either way", not "market risk exists").
5. **Not Financial Advice** — a short, explicit disclaimer that this is informational analysis, not a recommendation to buy or sell.

## Rules

- Every non-obvious number needs a source (see the `web-research` skill).
- State uncertainty plainly. "The data doesn't support a strong view either way" is a valid, useful conclusion.
- If sandboxed computation (returns, moving averages, volatility) was used, say what was computed and on what data, so the reasoning is checkable.
- Once the report is finalized, call the `render_content` tool with the markdown so it shows up in the analysis canvas — don't just leave it in the chat reply.
