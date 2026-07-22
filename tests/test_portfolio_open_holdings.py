"""Tests for open-holding filters used in portfolio analysis."""

from __future__ import annotations

from datetime import date

from services.portfolio_attention_service import AttentionItem, AttentionSummary
from services.portfolio_details_service import PortfolioDetailRow
from services.portfolio_open_holdings import (
    filter_attention_summary,
    filter_open_portfolio_rows,
)


def _row(*, ticker: str, shares: float) -> PortfolioDetailRow:
    return PortfolioDetailRow(
        company=ticker,
        ticker=ticker,
        market_cap=1e9,
        pe_ratio=15.0,
        shares=shares,
        current_price=100.0,
        current_value=100.0 * shares,
        avg_cost_per_share=90.0,
        acquisition_value=90.0 * shares,
        profit=10.0,
        profit_pct=10.0,
        estimated_avg_price=90.0,
        medium_price_365d=95.0,
        price_180d=98.0,
        price_365d=90.0,
        change_180d_pct=2.0,
        change_365d_pct=11.0,
        weight_pct=5.0,
        dividend_yield_pct=3.0,
        dividend_per_share=3.0,
        annual_income=30.0,
        dividend_weight_pct=5.0,
        income_weight_pct=5.0,
        dividends_paid=0.0,
        growth_years=10,
        commission=0.0,
        sector="Tech",
        acquisition_share_pct=5.0,
        analyst_rating="BUY",
        price_to_fcf=10.0,
        computed_dividend="3.00 (3.00%)",
        ex_dividend_date=None,
        dividend_pay_date=None,
        data_source="test",
    )


def test_filter_open_portfolio_rows_drops_sold_positions() -> None:
    active = _row(ticker="AAPL", shares=10.0)
    sold = _row(ticker="AMCR", shares=0.0)
    filtered = filter_open_portfolio_rows(
        [active, sold],
        allowed_symbols={"AAPL", "AMCR"},
    )
    assert [row.ticker for row in filtered] == ["AAPL"]


def test_filter_attention_summary_drops_sold_symbols() -> None:
    summary = AttentionSummary(
        risk_items=[
            AttentionItem(
                symbol="AAPL",
                company="Apple",
                severity="high",
                score=60,
                categories=("Exposure",),
                reasons=("Loss",),
            ),
            AttentionItem(
                symbol="AMCR",
                company="Amcor",
                severity="high",
                score=60,
                categories=("Exposure",),
                reasons=("Loss",),
            ),
        ],
        reference_date=date(2026, 5, 13),
    )
    filtered = filter_attention_summary(summary, allowed_symbols={"AAPL"})
    assert [item.symbol for item in filtered.risk_items] == ["AAPL"]


def test_reconcile_closed_holdings_drops_fully_sold_symbol(tmp_path) -> None:
    from data_ingestion.portfolio_store import PortfolioStore
    from data_ingestion.purchase_journal_store import PurchaseJournalStore
    from services.portfolio_open_holdings import reconcile_closed_holdings

    db = tmp_path / "portfolio.db"
    portfolio = PortfolioStore(db_path=db, seed=False)
    journal = PurchaseJournalStore(db_path=db, seed=False)
    portfolio.upsert_holding("AMCR", shares=20.0, avg_cost_per_share=10.0)
    journal.add_purchase(
        "AMCR",
        date(2024, 4, 1),
        10.0,
        shares=20.0,
        side="buy",
        source="ibkr",
    )
    journal.add_purchase(
        "AMCR",
        date(2024, 5, 1),
        11.0,
        shares=20.0,
        side="sell",
        source="ibkr",
    )

    dropped = reconcile_closed_holdings(db_path=db)

    assert dropped == ["AMCR"]
    assert portfolio.list_open_holdings() == []
    assert len(journal.list_purchases(portfolio_only=False)) == 2
