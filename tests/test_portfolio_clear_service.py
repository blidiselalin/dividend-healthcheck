"""Tests for portfolio clear service."""

from __future__ import annotations

from pathlib import Path

from services.portfolio_clear_service import clear_user_portfolio
from services.portfolio_context import create_portfolio_context


def test_clear_user_portfolio_wipes_all_tables(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    ctx = create_portfolio_context(db_path=db)
    ctx.portfolio.upsert_holding("AAPL", shares=10, avg_cost_per_share=150.0)
    ctx.journal.add_purchase("AAPL", __import__("datetime").date(2025, 1, 1), 150.0, shares=10)
    ctx.deposits.upsert_deposit(
        year=2025,
        month=1,
        label="Jan 2025",
        deposit_eur=1000.0,
        deposit_usd=1000.0,
        portfolio_eur=1000.0,
    )

    result = clear_user_portfolio(db_path=db)

    assert result.holdings >= 1
    assert result.journal >= 1
    assert result.deposits >= 1
    fresh = create_portfolio_context(db_path=db)
    assert fresh.portfolio.list_holdings() == []
    assert fresh.journal.list_purchases(portfolio_only=False) == []
    assert fresh.deposits.list_deposits() == []
