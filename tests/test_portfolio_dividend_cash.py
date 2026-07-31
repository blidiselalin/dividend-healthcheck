"""Tests for canonical dividend document resolution and warnings."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from data_ingestion.models import DividendRecord, StockDocument
from data_ingestion.portfolio_store import PortfolioHolding
from services.portfolio_dividend_cash import (
    build_merged_dividend_income_records,
    collect_dividend_data_warnings,
    resolve_dividend_documents,
    resolve_month_dividend_cash,
)
from services.portfolio_dividend_resolve import PortfolioDividendStatus


def _holding(symbol: str = "KO") -> PortfolioHolding:
    return PortfolioHolding(
        symbol=symbol,
        shares=10.0,
        avg_cost_per_share=50.0,
        acquisition_value=500.0,
        commission=0.0,
        dividends_paid=0.0,
        estimated_avg_price=50.0,
        sort_order=0,
    )


def test_resolve_dividend_documents_fills_missing_from_library() -> None:
    preload = SimpleNamespace(
        vector_docs={"KO": StockDocument(symbol="KO", name="KO", dividend_history=[])},
        dividend_statuses={},
    )
    pep_doc = StockDocument(
        symbol="PEP",
        name="Pepsi",
        dividend_history=[
            DividendRecord(ex_date=date(2026, 1, 15), payment_date=date(2026, 2, 1), amount=1.0),
        ],
    )

    ko_doc = StockDocument(symbol="KO", name="KO", dividend_history=[])
    with patch(
        "services.portfolio_dividend_resolve.load_resolved_portfolio_documents",
        return_value=({"KO": ko_doc, "PEP": pep_doc}, {}),
    ):
        docs, _ = resolve_dividend_documents([_holding("KO"), _holding("PEP")], preload)

    assert "KO" in docs
    assert "PEP" in docs
    assert len(docs["PEP"].dividend_history or []) == 1


def test_collect_warnings_flags_missing_history() -> None:
    holdings = [_holding("XYZ")]
    statuses = {
        "XYZ": PortfolioDividendStatus(
            symbol="XYZ",
            history_count=0,
            sources_checked=("market library",),
            sources_found=(),
            payment_date_sources=(),
        )
    }
    warnings = collect_dividend_data_warnings(holdings, {}, statuses)
    assert len(warnings) == 1
    assert warnings[0].level == "missing_history"
    assert warnings[0].symbol == "XYZ"


def test_resolve_month_dividend_cash_prefers_receipts() -> None:
    holding = _holding()
    doc = StockDocument(
        symbol="KO",
        name="KO",
        dividend_history=[
            DividendRecord(ex_date=date(2026, 6, 10), payment_date=date(2026, 6, 15), amount=0.5),
        ],
    )
    with (
        patch(
            "services.portfolio_month_dividends.gross_paid_in_calendar_month",
            return_value=(100.0, 2),
        ),
        patch(
            "services.portfolio_month_dividends.compute_month_received_from_holdings",
            return_value=(4.85, 1),
        ),
        patch(
            "services.portfolio_month_dividends.net_paid_in_calendar_month",
            return_value=None,
        ),
        patch(
            "services.portfolio_month_dividends.gross_paid_in_synced_month",
            return_value=None,
        ),
    ):
        cash = resolve_month_dividend_cash(
            year=2026,
            month=6,
            through=date(2026, 6, 19),
            holdings=[holding],
            vector_docs={"KO": doc},
        )
    assert cash.gross_usd == 100.0
    assert cash.payer_count == 2
    assert cash.source == "receipts"


def test_build_merged_dividend_income_records_fills_current_month_from_compute() -> None:
    today = date.today()
    store = SimpleNamespace(list_dividends=lambda: [])
    receipts = SimpleNamespace(monthly_gross_totals=lambda: {})
    ctx = SimpleNamespace(
        dividends=store,
        receipts=receipts,
        portfolio=SimpleNamespace(list_open_holdings=lambda: [_holding()]),
    )

    with (
        patch(
            "services.portfolio_context.create_portfolio_context",
            return_value=ctx,
        ),
        patch(
            "services.portfolio_dividend_cash.resolve_dividend_documents",
            return_value=({}, {}),
        ),
        patch(
            "services.portfolio_dividend_cash.resolve_month_dividend_cash",
            return_value=SimpleNamespace(
                gross_usd=42.0, net_usd=37.8, payer_count=2, source="computed"
            ),
        ),
    ):
        records = build_merged_dividend_income_records(
            store=store,
            receipt_store=receipts,
            holdings=[_holding()],
            preload=None,
        )

    current = [item for item in records if item.year == today.year and item.month == today.month]
    assert len(current) == 1
    assert current[0].gross_usd == 42.0
    assert current[0].net_usd == 37.8
