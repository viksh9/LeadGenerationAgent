"""Process-wide logging setup."""

from __future__ import annotations

import logging
import sys

from config.settings import get_settings

DEFAULT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
DEFAULT_DATEFMT = "%Y-%m-%dT%H:%M:%S"


def configure_logging(level: str | None = None) -> None:
    """Configure root logging once for API, pipeline, and CLI usage."""
    settings = get_settings()
    resolved = (level or settings.log_level).upper()
    numeric = getattr(logging, resolved, logging.INFO)
    logging.basicConfig(
        level=numeric,
        format=DEFAULT_FORMAT,
        datefmt=DEFAULT_DATEFMT,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
