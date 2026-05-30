"""
Small demo portfolio for the test user (no live API required for first paint).
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

# symbol, company, shares, avg_cost_usd
DEMO_HOLDINGS: List[Tuple[str, str, float, float]] = [
    ("KO", "Coca-Cola Co", 25.0, 58.0),
    ("JNJ", "Johnson & Johnson", 10.0, 155.0),
    ("O", "Realty Income Corp", 30.0, 52.0),
]

DEMO_DEPOSITS: List[Tuple[int, int, str, float, float, float]] = [
    (2024, 1, "January 2024", 1000.0, 1080.0, 4200.0),
    (2024, 6, "June 2024", 1500.0, 1620.0, 5100.0),
    (2024, 12, "December 2024", 2000.0, 2160.0, 5800.0),
    (2025, 6, "June 2025", 1500.0, 1620.0, 6200.0),
]


def _holding_count(db_path: Path) -> int:
    from utils.portfolio_db import holding_count

    return holding_count(db_path)


def ensure_demo_database(db_path: Path) -> bool:
    """
    Seed demo holdings and deposits when the test user's DB is empty.

    Returns True when seed data was written.
    """
    from data_ingestion.deposits_store import DepositsStore
    from data_ingestion.portfolio_store import PortfolioStore
    from db.connection import use_cloud_sql

    db_path = Path(db_path)
    if not use_cloud_sql():
        db_path.parent.mkdir(parents=True, exist_ok=True)

    seeded = False
    store = PortfolioStore(db_path=db_path, seed=False)
    if _holding_count(db_path) == 0:
        for index, (symbol, company, shares, avg_cost) in enumerate(DEMO_HOLDINGS, start=1):
            store.upsert_holding(
                symbol,
                shares=shares,
                avg_cost_per_share=avg_cost,
                company_name=company,
            )
        seeded = True
        logger.info("Seeded demo holdings at %s", db_path)

    deposits = DepositsStore(db_path=db_path, seed=False)
    if not deposits.list_deposits():
        with deposits._connect() as connection:
            for index, (year, month, label, eur, usd, port) in enumerate(
                DEMO_DEPOSITS, start=1
            ):
                period_key = f"{year:04d}-{month:02d}"
                connection.execute(
                    """
                    INSERT OR IGNORE INTO monthly_deposits (
                      period_key, year, month, label,
                      deposit_eur, deposit_usd, portfolio_eur, sort_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (period_key, year, month, label, eur, usd, port, index),
                )
        seeded = True

    return seeded


def reset_demo_database(db_path: Path) -> None:
    """Remove test user's DB and session cache so the next login re-seeds."""
    db_path = Path(db_path)
    cache = db_path.parent / "portfolio_ui_session.pkl"
    if db_path.is_file():
        db_path.unlink()
    if cache.is_file():
        cache.unlink()


def load_demo_ui_snapshot() -> bool:
    """Build cached portfolio rows from demo DB (no live Yahoo fetch)."""
    try:
        import streamlit as st
    except Exception:
        return False

    from services.portfolio_details_service import PortfolioDetailsService
    from ui.portfolio_risk_panel import store_portfolio_payload

    if st.session_state.get("portfolio_details_rows"):
        return True

    try:
        rows, preload = PortfolioDetailsService().build_rows_with_cache(
            use_live_prices=False
        )
    except Exception as exc:
        logger.warning("Demo UI snapshot failed: %s", exc)
        return False

    if not rows:
        return False

    store_portfolio_payload(rows, preload)
    return True
