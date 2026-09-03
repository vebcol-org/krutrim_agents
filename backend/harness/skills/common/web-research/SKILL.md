---
name: web-research
description: Structured approach to researching a company, market, or asset before producing analysis. Use whenever a request needs facts, prices, news, or filings that aren't already in context.
license: MIT
---

# Web Research

## When to Use

- The user asks about a company, ticker, sector, or macro event you don't already have current information on.
- You need to verify a claim (a price, a date, an earnings number) before including it in analysis.

## How to Use

1. Call `web_search` with a focused query (ticker + topic, e.g. `"AAPL Q3 2025 earnings guidance"`) rather than a broad one.
2. When a result looks load-bearing for the analysis, call `web_fetch` on the specific source to read the full page rather than relying on the search snippet alone.
3. Note the source and retrieval time for every fact you plan to use — the writer subagent needs this to cite sources in the final report.
4. Prefer primary sources (exchange filings, company press releases, official statistics) over aggregator commentary when both are available.
5. If search results conflict, say so explicitly rather than silently picking one.

## Output

Hand off findings as short, sourced notes (claim → source → retrieved-at), not raw dumps of search results — the next agent in the pipeline should not have to re-derive what mattered.
