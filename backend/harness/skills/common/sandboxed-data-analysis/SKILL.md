---
name: sandboxed-data-analysis
description: How to run computations (returns, moving averages, volatility, backtests) using the sandboxed execute tool. Use whenever a claim needs arithmetic on a series of numbers rather than a lookup.
license: MIT
---

# Sandboxed Data Analysis

## When to Use

Any time you're about to compute something numeric from a series of values (returns, averages, correlations, simple backtests) — don't do the arithmetic in your head, run it.

## How to Use

1. Write the data you're working with to `/workspace/<name>.csv` (via `write_file`) or generate it inline in a script.
2. Use `execute` to run a Python script (`python3 -c "..."` or write a `.py` file and run it) with `pandas`/`numpy`, both pre-installed in the sandbox.
3. The sandbox has **no network access** — any data the script needs must already be in `/workspace` (written by you from earlier research) or generated synthetically. Don't write code that tries to fetch URLs from inside `execute`; use the `fetch_url`/`web_search` tools for that instead, then feed the results in as data.
4. Read results back with `read_file` or print them directly as `execute` output.
5. Report exactly what was computed (formula, inputs, time window) alongside the number — a bare number without provenance isn't useful in the final report.
