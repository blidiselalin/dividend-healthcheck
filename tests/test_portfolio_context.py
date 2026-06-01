"""Tests for portfolio context wiring."""

from __future__ import annotations

from services.portfolio_context import create_portfolio_context


def test_portfolio_context_shares_db_path(tmp_path):
    db = tmp_path / "portfolio.db"
    ctx = create_portfolio_context(db_path=db)
    assert ctx.portfolio.db_path == ctx.journal.db_path == ctx.receipts.db_path == db
