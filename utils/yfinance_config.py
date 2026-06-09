"""
Docker-safe yfinance cache path and log noise reduction.

yfinance defaults to ``~/.cache/py-yfinance`` which can fail in containers when
that path exists as a file or is not writable. Configure a data-dir cache before
any ticker fetch, and filter known benign warnings from docker logs.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

_CONFIGURED = False


class YfinanceNoiseFilter(logging.Filter):
    """Drop repetitive yfinance cache/delisted messages that are not actionable."""

    _NEEDLES = (
        "TzCache",
        "Failed to create TzCache",
        "possibly delisted",
        "No timezone found",
        "No price data found",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(needle in message for needle in self._NEEDLES)


def yfinance_cache_dir() -> Path:
    try:
        from config import DATA_DIR

        return Path(DATA_DIR) / "cache" / "yfinance"
    except ImportError:
        return Path(os.environ.get("DIVIDENDSCOPE_DATA_DIR", "/data")) / "cache" / "yfinance"


def configure_yfinance() -> None:
    """Set cache location and attach log filters (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    cache_dir = yfinance_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        import yfinance as yf

        yf.set_tz_cache_location(str(cache_dir))
    except ImportError:
        pass
    except Exception as exc:
        logging.getLogger(__name__).debug("yfinance cache setup skipped: %s", exc)

    noise_filter = YfinanceNoiseFilter()
    for name in ("yfinance", "yfinance.base", "yfinance.scrapers", "peewee"):
        logger = logging.getLogger(name)
        if not any(isinstance(filt, YfinanceNoiseFilter) for filt in logger.filters):
            logger.addFilter(noise_filter)
