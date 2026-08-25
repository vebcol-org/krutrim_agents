"""Snapshots the backend's OpenAPI spec to `backend/docs/openapi.json` — the
live version is always served at `GET /openapi.json` (and Swagger UI at
`/docs`) by the running backend; this is a static copy for anyone browsing
`backend/docs/` without a server running.

Run from `backend/`:

    uv run python scripts/export_openapi.py

Re-run and commit whenever a route's request/response shape changes.
"""

from __future__ import annotations

import json
from pathlib import Path

from krutrim_agent_backend.main import app

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"


def main() -> None:
    spec = app.openapi()
    OUTPUT_PATH.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
