"""
Wipe all portfolio-local tables for the current user (full replace before broker import).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from services.portfolio_context import create_portfolio_context

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PortfolioClearResult:
    holdings: int
    journal: int
    receipts: int
    net_dividends: int
    deposits: int

    @property
    def total_rows(self) -> int:
        return self.holdings + self.journal + self.receipts + self.net_dividends + self.deposits


def _clear_session_caches() -> None:
    try:
        from services.portfolio_session import reset_portfolio_view_state

        reset_portfolio_view_state()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not reset portfolio view state: %s", exc)


def clear_user_portfolio(*, db_path: Path | None = None) -> PortfolioClearResult:
    """Delete all holdings, journal, receipts, net dividends, and deposits."""
    ctx = create_portfolio_context(db_path=db_path)
    receipts = ctx.receipts.delete_all()
    journal = ctx.journal.delete_all()
    net_dividends = ctx.dividends.delete_all()
    deposits = ctx.deposits.delete_all()
    holdings = ctx.portfolio.delete_all()
    _clear_session_caches()
    result = PortfolioClearResult(
        holdings=holdings,
        journal=journal,
        receipts=receipts,
        net_dividends=net_dividends,
        deposits=deposits,
    )
    logger.info(
        "Cleared portfolio: holdings=%d journal=%d receipts=%d net=%d deposits=%d",
        result.holdings,
        result.journal,
        result.receipts,
        result.net_dividends,
        result.deposits,
    )
    return result
