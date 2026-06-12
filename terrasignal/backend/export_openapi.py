"""Dump the FastAPI OpenAPI spec to a file without running a server.

The frontend's TypeScript types are generated from this artifact, so it is the
single source of truth for the client/server contract. CI runs this and fails
if `frontend/openapi.json` (and the generated types) drift from the backend
schemas — contracts are generated, never hand-written (CLAUDE.md §3).

    python -m terrasignal.backend.export_openapi [OUTPUT_PATH]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from terrasignal.backend.app.main import app

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "frontend" / "openapi.json"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    spec = app.openapi()
    out.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(spec['paths'])} paths)")  # noqa: T201 — CLI tool


if __name__ == "__main__":
    main()
