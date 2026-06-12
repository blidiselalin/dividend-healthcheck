"""Tests for portfolio context wiring."""
# ruff: noqa: S101

from __future__ import annotations

from pathlib import Path

from services.portfolio_context import create_portfolio_context


def test_portfolio_context_shares_db_path(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    ctx = create_portfolio_context(db_path=db)
    assert ctx.portfolio.db_path == ctx.journal.db_path == ctx.receipts.db_path == db
