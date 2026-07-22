"""Tests for holding purchase/dividend drill-down."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date

from data_ingestion.models import DividendRecord, StockDocument
from services.portfolio_holding_detail_service import (
    HoldingDividendRow,
    PortfolioHoldingDetailService,
    shares_as_of,
)
from services.portfolio_purchase_journal_service import EstimatedPurchaseLot


def test_shares_as_of_accumulates_lots() -> None:
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


def test_shares_as_of_respects_sell_before_ex_date() -> None:
    lots = [
        EstimatedPurchaseLot(
            symbol="AAPL",
            purchase_date=date(2025, 1, 1),
            label="01 Jan 2025",
            price_usd=150.0,
            estimated_shares=10.0,
            estimated_value_usd=1500.0,
        ),
        EstimatedPurchaseLot(
            symbol="AAPL",
            purchase_date=date(2025, 5, 1),
            label="01 May 2025",
            price_usd=160.0,
            estimated_shares=-3.0,
            estimated_value_usd=-480.0,
        ),
    ]
    assert shares_as_of(lots, date(2025, 3, 1), fallback_shares=99) == 10.0
    assert shares_as_of(lots, date(2025, 6, 1), fallback_shares=99) == 7.0


def test_dividend_cash_uses_shares_at_ex_date() -> None:
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


def test_dividend_history_uses_shares_after_partial_sell() -> None:
    service = PortfolioHoldingDetailService()
    doc = type("Doc", (), {})()
    doc.dividend_history = [
        DividendRecord(
            ex_date=date(2025, 3, 1),
            payment_date=date(2025, 3, 15),
            amount=0.25,
        ),
        DividendRecord(
            ex_date=date(2025, 7, 1),
            payment_date=date(2025, 7, 15),
            amount=0.25,
        ),
    ]
    lots = [
        EstimatedPurchaseLot(
            symbol="AAPL",
            purchase_date=date(2025, 1, 1),
            label="01 Jan 2025",
            price_usd=150.0,
            estimated_shares=10.0,
            estimated_value_usd=1500.0,
        ),
        EstimatedPurchaseLot(
            symbol="AAPL",
            purchase_date=date(2025, 5, 1),
            label="01 May 2025",
            price_usd=160.0,
            estimated_shares=-3.0,
            estimated_value_usd=-480.0,
        ),
    ]
    service.estimated_lots_for_symbol = lambda symbol: lots if symbol == "AAPL" else []
    rows = service.dividend_history("AAPL", doc, current_shares=7.0)
    assert [row.shares_held for row in rows] == [10.0, 7.0]
    assert [row.cash_usd for row in rows] == [2.5, 1.75]


def test_purchases_dataframe_marks_sell_rows() -> None:
    service = PortfolioHoldingDetailService()
    service.purchase_history = lambda symbol: [
        type(
            "Row",
            (),
            {
                "label": "01 Jan 2025",
                "price_usd": 150.0,
                "estimated_shares": 10.0,
                "estimated_cost_usd": 1500.0,
                "cumulative_shares": 10.0,
            },
        )(),
        type(
            "Row",
            (),
            {
                "label": "01 May 2025",
                "price_usd": 160.0,
                "estimated_shares": -3.0,
                "estimated_cost_usd": -480.0,
                "cumulative_shares": 7.0,
            },
        )(),
    ]
    frame = service.purchases_dataframe("AAPL")
    assert list(frame["Side"]) == ["Buy", "Sell"]
    assert frame.iloc[1]["Shares"] == -3.0


def test_dividends_dataframe_passes_tracking_since() -> None:
    service = PortfolioHoldingDetailService()
    captured: dict = {}

    def fake_history(
        symbol: str,
        document: StockDocument | None,
        *,
        current_shares: float,
        tracking_since: date | None,
        prefer_stored: bool,
    ) -> list[HoldingDividendRow]:
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
