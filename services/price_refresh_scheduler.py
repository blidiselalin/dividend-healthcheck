"""
Background price refresh — keep shared library current_price updated every 5 minutes.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_started = False
_start_lock = threading.Lock()
_run_lock = threading.Lock()
_last_stats: dict[str, Any] | None = None
_last_run_at: datetime | None = None
_last_error: str | None = None
_interval_seconds: int = 300


def _scheduler_disabled() -> bool:
    flag = os.environ.get("DIVIDENDSCOPE_DISABLE_PRICE_SCHEDULER", "").strip().lower()
    if flag in ("1", "true", "yes"):
        return True
    if os.environ.get("PYTEST_USE_SQLITE") == "1":
        return True
    return False


def _resolve_interval_seconds(interval_seconds: int | None = None) -> int:
    if interval_seconds is not None:
        return max(60, int(interval_seconds))
    override = os.environ.get("DIVIDENDSCOPE_PRICE_REFRESH_SECONDS", "").strip()
    if override.isdigit():
        return max(60, int(override))
    from config import PRICE_REFRESH_INTERVAL_SECONDS

    return max(60, int(PRICE_REFRESH_INTERVAL_SECONDS))


def run_price_refresh_once() -> dict[str, Any]:
    """Refresh live quotes for all library + portfolio symbols (single pass)."""
    global _last_stats, _last_run_at, _last_error

    if not _run_lock.acquire(blocking=False):
        logger.info("Price refresh skipped: previous run still active")
        return {"skipped": True, "reason": "already_running"}

    try:
        from services.db_price_refresh import refresh_market_library_prices

        stats = refresh_market_library_prices()
        _last_stats = stats
        _last_run_at = datetime.now()
        _last_error = None
        logger.info(
            "Price refresh complete: updated=%s skipped=%s errors=%s total=%s",
            stats.get("updated"),
            stats.get("skipped"),
            stats.get("errors"),
            stats.get("total"),
        )
        return stats
    except Exception as exc:
        _last_error = str(exc)
        logger.exception("Price refresh failed")
        raise
    finally:
        _run_lock.release()


def _refresh_loop(interval_seconds: int) -> None:
    from utils.yfinance_config import configure_yfinance

    configure_yfinance()
    logger.info("Price refresh scheduler started (every %ss)", interval_seconds)

    while True:
        import contextlib

        with contextlib.suppress(Exception):
            run_price_refresh_once()
        time.sleep(interval_seconds)


def start_price_refresh_scheduler(*, interval_seconds: int | None = None) -> bool:
    """
    Start the daemon price refresh thread once per process.

    Returns True when the scheduler was started on this call.
    """
    global _started, _interval_seconds

    if _scheduler_disabled():
        return False

    with _start_lock:
        if _started:
            return False
        _interval_seconds = _resolve_interval_seconds(interval_seconds)
        thread = threading.Thread(
            target=_refresh_loop,
            args=(_interval_seconds,),
            daemon=True,
            name="price-refresh",
        )
        thread.start()
        _started = True
        return True


def scheduler_status() -> dict[str, Any]:
    """Snapshot for admin UI and health checks."""
    return {
        "enabled": not _scheduler_disabled(),
        "running": _started,
        "interval_seconds": _interval_seconds,
        "last_run_at": _last_run_at.isoformat(timespec="seconds") if _last_run_at else None,
        "last_stats": dict(_last_stats) if _last_stats else None,
        "last_error": _last_error,
    }
