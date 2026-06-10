"""Tests for holding purchase/dividend drill-down."""

from __future__ import annotations

from datetime import date

from data_ingestion.models import DividendRecord
from services.portfolio_holding_detail_service import (
    PortfolioHoldingDetailService,
    shares_as_of,
)
from services.portfolio_purchase_journal_service import EstimatedPurchaseLot


def test_shares_as_of_accumulates_lots():
    lots = [
        EstimatedPurchaseLot(
            symbol="X",
            purchase_date=date(2024, 1, 1),
            label="01 Jan 2024",
            price_usd=10.0,
            estimated_shares=5.0,
            estimated_value_usd=50.0,
        ),
        EstimatedPurchaseLot(
            symbol="X",
            purchase_date=date(2024, 6, 1),
            label="01 Jun 2024",
            price_usd=12.0,
            estimated_shares=5.0,
            estimated_value_usd=60.0,
        ),
    ]
    assert shares_as_of(lots, date(2024, 3, 1), fallback_shares=99) == 5.0
    assert shares_as_of(lots, date(2024, 7, 1), fallback_shares=99) == 10.0


def test_dividend_cash_uses_shares_at_ex_date():
    service = PortfolioHoldingDetailService()
    doc = type("Doc", (), {})()
    doc.dividend_history = [
        DividendRecord(
            ex_date=date(2024, 8, 1),
            payment_date=date(2024, 8, 15),
            amount=1.0,
        ),
    ]
    lots = [
        EstimatedPurchaseLot(
            symbol="KO",
            purchase_date=date(2024, 1, 1),
            label="01 Jan 2024",
            price_usd=50.0,
            estimated_shares=10.0,
            estimated_value_usd=500.0,
        ),
    ]
    service.estimated_lots_for_symbol = lambda symbol: lots if symbol == "KO" else []
    rows = service.dividend_history("KO", doc, current_shares=10.0)
    assert len(rows) == 1
    assert rows[0].shares_held == 10.0
    assert rows[0].cash_usd == 10.0


def test_dividends_dataframe_passes_tracking_since():
    service = PortfolioHoldingDetailService()
    captured: dict = {}

    def fake_history(symbol, document, *, current_shares, tracking_since, prefer_stored):
        captured["tracking_since"] = tracking_since
        captured["prefer_stored"] = prefer_stored
        return []

    service.dividend_history = fake_history
    frame = service.dividends_dataframe(
        "KO",
        None,
        current_shares=10.0,
        tracking_since=date(2024, 1, 1),
    )
    assert captured["tracking_since"] == date(2024, 1, 1)
    assert captured["prefer_stored"] is True
    assert frame.empty
