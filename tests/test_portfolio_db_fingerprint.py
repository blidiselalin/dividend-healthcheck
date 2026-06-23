"""Portfolio DB fingerprint for session freshness checks."""

from __future__ import annotations

from pathlib import Path

from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore
from utils.portfolio_db import compute_portfolio_db_fingerprint, invalidate_portfolio_db_fingerprint_cache


def test_fingerprint_changes_when_holding_updated(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    store = PortfolioStore(db_path=db, seed=False)
    store.upsert_holding("KO", shares=10.0, avg_cost_per_share=50.0)
    invalidate_portfolio_db_fingerprint_cache()
    before = compute_portfolio_db_fingerprint(db, use_cache=False)

    store.update_holding("KO", shares=12.0)
    invalidate_portfolio_db_fingerprint_cache()
    after = compute_portfolio_db_fingerprint(db, use_cache=False)

    assert before != after


def test_fingerprint_changes_when_purchase_logged(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    store = PortfolioStore(db_path=db, seed=False)
    store.upsert_holding("KO", shares=10.0, avg_cost_per_share=50.0)
    journal = PurchaseJournalStore(db_path=db, seed=False)
    invalidate_portfolio_db_fingerprint_cache()
    before = compute_portfolio_db_fingerprint(db, use_cache=False)

    journal.add_purchase("KO", __import__("datetime").date(2024, 1, 1), 49.0)
    invalidate_portfolio_db_fingerprint_cache()
    after = compute_portfolio_db_fingerprint(db, use_cache=False)

    assert before != after
