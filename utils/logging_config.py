"""
Application logging for Docker / stdout (docker logs -f dividendscope).

Set level via DIVIDENDSCOPE_LOG_LEVEL (default INFO).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

_CONFIGURED = False

_DEFAULT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"


def configure_app_logging(level: Optional[str] = None) -> None:
    """Configure root logging once; safe to call on every Streamlit rerun."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    raw = (level or os.environ.get("DIVIDENDSCOPE_LOG_LEVEL", "INFO")).strip().upper()
    log_level = getattr(logging, raw, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(_DEFAULT_FORMAT, datefmt=_DEFAULT_DATEFMT)
    )

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(handler)

    for noisy in ("streamlit", "urllib3", "httpx", "httpcore", "chromadb", "watchdog"):
        logging.getLogger(noisy).setLevel(max(log_level, logging.WARNING))

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_app_logging()
    return logging.getLogger(name)
