"""Date/time tools shared across agent profiles."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.tools import tool


def _resolve_timezone(timezone: str | None):
    """Return a ZoneInfo for the given name, or the system's local timezone if None."""
    if timezone is None:
        return datetime.now().astimezone().tzinfo
    return ZoneInfo(timezone)


@tool
def get_current_date(timezone: str | None = None) -> str:
    """Get the current date (YYYY-MM-DD).

    Args:
        timezone: Optional IANA timezone name, e.g. "America/New_York".
            If omitted, uses the system's local timezone.
    """
    try:
        tz = _resolve_timezone(timezone)
    except Exception:
        return f"Error: unknown timezone '{timezone}'"
    return datetime.now(tz).date().isoformat()


@tool
def get_current_time(timezone: str | None = None) -> str:
    """Get the current time (HH:MM:SS).

    Args:
        timezone: Optional IANA timezone name, e.g. "America/New_York".
            If omitted, uses the system's local timezone.
    """
    try:
        tz = _resolve_timezone(timezone)
    except Exception:
        return f"Error: unknown timezone '{timezone}'"
    return datetime.now(tz).strftime("%H:%M:%S")


@tool
def get_current_datetime(timezone: str | None = None) -> str:
    """Get the current date and time (ISO 8601), including UTC offset.

    Args:
        timezone: Optional IANA timezone name, e.g. "America/New_York".
            If omitted, uses the system's local timezone.
    """
    try:
        tz = _resolve_timezone(timezone)
    except Exception:
        return f"Error: unknown timezone '{timezone}'"
    return datetime.now(tz).isoformat()
