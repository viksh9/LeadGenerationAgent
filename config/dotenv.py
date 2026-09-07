"""Minimal, dependency-free .env loader for CLI entry points.

Loads simple KEY=VALUE lines from a local .env into os.environ so that
environment-based source configs (Adzuna, Jooble, …) pick up credentials when a
collector CLI is run. Existing environment variables always win, and values are
never logged. Not used by the API server (which reads settings via pydantic).
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    path = path or (ROOT_DIR / ".env")
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        # Skip empty values so optional toggles left blank in .env don't turn into
        # empty-string env vars (which would fail bool/int parsing downstream).
        if key and value and key not in os.environ:
            os.environ[key] = value
