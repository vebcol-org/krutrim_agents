"""General-purpose research tools shared across agent profiles.

File I/O is *not* defined here — deepagents provisions
`ls`/`read_file`/`write_file`/`edit_file`/`glob`/`grep` automatically from the
filesystem backend (see `krutrim_agents_core.builder`).

`web_search`/`web_fetch`/`get_current_date`/`get_current_time`/
`get_current_datetime` re-export the same names the old flat `tools.py`
module exported — every profile's `from krutrim_agents_core.tools import ...`
import keeps working unchanged. Import a specific provider directly (e.g.
`from krutrim_agents_core.tools.websearch import tavily_search`) to pin one
explicitly instead of using the configured default.
"""

from __future__ import annotations

from .datetime_tools import get_current_date, get_current_datetime, get_current_time
from .fetch import web_fetch
from .websearch import get_web_search_tool, tavily_search, web_search

__all__ = [
    "get_current_date",
    "get_current_datetime",
    "get_current_time",
    "get_web_search_tool",
    "tavily_search",
    "web_fetch",
    "web_search",
]
