"""
Small demo portfolio for the test user (no live API required for first paint).
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# symbol, company, shares, avg_cost_usd
DEMO_HOLDINGS: list[tuple[str, str, float, float]] = [
    ("KO", "Coca-Cola Co", 25.0, 58.0),
    ("JNJ", "Johnson & Johnson", 10.0, 155.0),
    ("O", "Realty Income Corp", 30.0, 52.0),
]

DEMO_DEPOSITS: list[tuple[int, int, str, float, float, float]] = [
    (2024, 1, "January 2024", 1000.0, 1080.0, 4200.0),
    (2024, 6, "June 2024", 1500.0, 1620.0, 5100.0),
    (2024, 12, "December 2024", 2000.0, 2160.0, 5800.0),
    (2025, 6, "June 2025", 1500.0, 1620.0, 6200.0),
]


def _portfolio_context(db_path: Path):
    from services.portfolio_context import create_portfolio_context

    return create_portfolio_context(db_path=db_path)


def ensure_demo_database(db_path: Path) -> bool:
    """
    Seed demo holdings and deposits when the test user's DB is empty.

    Returns True when seed data was written.
    """
    from db.connection import use_cloud_sql
    from utils.portfolio_db import holding_count

    db_path = Path(db_path)
    if not use_cloud_sql():
        db_path.parent.mkdir(parents=True, exist_ok=True)

    ctx = _portfolio_context(db_path)
    seeded = False

    if holding_count(db_path) == 0:
        for symbol, company, shares, avg_cost in DEMO_HOLDINGS:
            ctx.portfolio.upsert_holding(
                symbol,
                shares=shares,
                avg_cost_per_share=avg_cost,
                company_name=company,
            )
        seeded = True
        logger.info("Seeded demo holdings at %s", db_path)

    if not ctx.deposits.list_deposits():
        for year, month, label, eur, usd, port in DEMO_DEPOSITS:
            ctx.deposits.upsert_deposit(
                year=year,
                month=month,
                label=label,
                deposit_eur=eur,
                deposit_usd=usd,
                portfolio_eur=port,
            )
        seeded = True

    return seeded


def reset_demo_database(db_path: Path) -> None:
    """Remove test user's portfolio data and session cache so the next login re-seeds."""
    from db.connection import use_cloud_sql

    db_path = Path(db_path)
    cache = db_path.parent / "portfolio_ui_session.pkl"

    if use_cloud_sql():
        ctx = _portfolio_context(db_path)
        for holding in list(ctx.portfolio.list_holdings()):
            ctx.portfolio.delete_holding(holding.symbol)
        for deposit in list(ctx.deposits.list_deposits()):
            ctx.deposits.delete_deposit(deposit.period_key)
        for purchase in list(ctx.journal.list_purchases(portfolio_only=False)):
            ctx.journal.delete_purchase(purchase.id)
    elif db_path.is_file():
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
        rows, preload = PortfolioDetailsService().build_rows_with_cache(use_live_prices=False)
    except Exception as exc:
        logger.warning("Demo UI snapshot failed: %s", exc)
        return False

    if not rows:
        return False

    store_portfolio_payload(rows, preload)
    return True
