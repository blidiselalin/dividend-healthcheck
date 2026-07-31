"""Monthly portfolio dividend calendar — amounts, months, and share counts."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from data_ingestion.models import DividendRecord, StockDocument
from data_ingestion.portfolio_store import PortfolioHolding
from services.portfolio_dividend_calendar import build_portfolio_dividend_calendar


@pytest.fixture(autouse=True)
def _no_journal_lots(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use holding.shares in unit tests (no portfolio DB journal interference)."""
    monkeypatch.setattr(
        "services.portfolio_holding_detail_service.PortfolioHoldingDetailService.estimated_lots_for_symbol",
        lambda self, symbol: [],
    )


def _monthly_records(amount: float = 0.27) -> list[DividendRecord]:
    return [
        DividendRecord(
            ex_date=date(2025, month, 15),
            payment_date=date(2025, month, 28),
            amount=amount,
        )
        for month in range(1, 13)
    ] + [
        DividendRecord(
            ex_date=date(2026, month, 15),
            payment_date=date(2026, month, 28),
            amount=amount,
        )
        for month in range(1, 6)
    ]


def _quarterly_records(amount: float = 0.48) -> list[DividendRecord]:
    months = (3, 6, 9, 12)
    records: list[DividendRecord] = []
    for year in (2024, 2025, 2026):
        for month in months:
            if year == 2026 and month > 6:
                continue
            records.append(
                DividendRecord(
                    ex_date=date(year, month, 10),
                    payment_date=date(year, month, 25),
                    amount=amount,
                )
            )
    return records


def test_monthly_portfolio_june_matches_annual_divided_by_twelve() -> None:
    holdings = [
        PortfolioHolding(
            symbol="O",
            shares=30.0,
            avg_cost_per_share=52.0,
            acquisition_value=1560.0,
            commission=0.0,
            dividends_paid=0.0,
            estimated_avg_price=52.0,
            sort_order=0,
            company_name="Realty Income",
        ),
        PortfolioHolding(
            symbol="STAG",
            shares=20.0,
            avg_cost_per_share=35.0,
            acquisition_value=700.0,
            commission=0.0,
            dividends_paid=0.0,
            estimated_avg_price=35.0,
            sort_order=1,
            company_name="STAG Industrial",
        ),
    ]
    docs = {
        "O": StockDocument(
            symbol="O",
            name="Realty Income",
            dividend_history=_monthly_records(0.27),
            payment_frequency=12,
        ),
        "STAG": StockDocument(
            symbol="STAG",
            name="STAG Industrial",
            dividend_history=_monthly_records(0.12),
            payment_frequency=12,
        ),
    }
    calendar = build_portfolio_dividend_calendar(
        holdings,
        vector_docs=docs,
        stock_data={},
        reference_date=date(2026, 6, 19),
    )
    june = calendar.current_month
    expected = round((0.27 * 30) + (0.12 * 20), 2)
    assert june.confirmed_cash == expected
    assert june.payer_count == 2
    assert june.projected_cash == 0.0


def test_quarterly_stock_not_projected_into_non_payment_month() -> None:
    holding = PortfolioHolding(
        symbol="KO",
        shares=25.0,
        avg_cost_per_share=58.0,
        acquisition_value=1450.0,
        commission=0.0,
        dividends_paid=0.0,
        estimated_avg_price=58.0,
        sort_order=0,
        company_name="Coca-Cola",
    )
    doc = StockDocument(
        symbol="KO",
        name="Coca-Cola",
        dividend_history=_quarterly_records(0.485),
        payment_frequency=4,
    )
    calendar = build_portfolio_dividend_calendar(
        [holding],
        vector_docs={"KO": doc},
        stock_data={},
        reference_date=date(2026, 5, 19),
    )
    assert calendar.current_month.payer_count == 0
    assert calendar.current_month.total_cash == 0.0

    june = build_portfolio_dividend_calendar(
        [holding],
        vector_docs={"KO": doc},
        stock_data={},
        reference_date=date(2026, 6, 19),
    ).current_month
    assert june.payer_count == 1
    assert june.confirmed_cash == round(0.485 * 25, 2)


def test_annual_lump_in_history_is_normalized_to_per_payment() -> None:
    holding = PortfolioHolding(
        symbol="VZ",
        shares=10.0,
        avg_cost_per_share=40.0,
        acquisition_value=400.0,
        commission=0.0,
        dividends_paid=0.0,
        estimated_avg_price=40.0,
        sort_order=0,
        company_name="Verizon",
    )
    records = _quarterly_records(0.6775)
    records.append(
        DividendRecord(
            ex_date=date(2026, 6, 10),
            payment_date=date(2026, 6, 25),
            amount=2.71,  # annual total stored by mistake
        )
    )
    doc = StockDocument(
        symbol="VZ",
        name="Verizon",
        dividend_history=records,
        payment_frequency=4,
        annual_dividend=2.71,
    )
    june = build_portfolio_dividend_calendar(
        [holding],
        vector_docs={"VZ": doc},
        stock_data={},
        reference_date=date(2026, 6, 19),
    ).current_month
    assert june.confirmed_cash == round(0.6775 * 10, 2)


def test_last_month_uses_actual_history_only() -> None:
    holding = PortfolioHolding(
        symbol="KO",
        shares=25.0,
        avg_cost_per_share=58.0,
        acquisition_value=1450.0,
        commission=0.0,
        dividends_paid=0.0,
        estimated_avg_price=58.0,
        sort_order=0,
    )
    doc = StockDocument(
        symbol="KO",
        name="Coca-Cola",
        dividend_history=_quarterly_records(0.485),
        payment_frequency=4,
    )
    calendar = build_portfolio_dividend_calendar(
        [holding],
        vector_docs={"KO": doc},
        stock_data={},
        reference_date=date(2026, 6, 19),
    )
    assert calendar.last_month.payer_count == 0
    assert calendar.last_month.total_cash == 0.0


def test_enrich_calendar_overlays_imported_receipts(tmp_path: Path) -> None:
    from services.portfolio_broker_import_service import ImportMode, apply_import
    from services.portfolio_context import create_portfolio_context
    from services.portfolio_dividend_calendar import enrich_calendar_with_receipts

    fixture = Path(__file__).resolve().parents[0] / "fixtures" / "ibkr_activity_sample.csv"
    db = tmp_path / "portfolio.db"
    apply_import(fixture.read_text(encoding="utf-8"), mode=ImportMode.REPLACE, db_path=db)
    ctx = create_portfolio_context(db_path=db)
    holdings = ctx.portfolio.list_open_holdings()
    calendar = build_portfolio_dividend_calendar(
        holdings,
        vector_docs={},
        stock_data={},
        reference_date=date(2025, 4, 15),
    )
    assert calendar.last_month.total_cash == 0.0

    enrich_calendar_with_receipts(calendar, holdings, receipt_store=ctx.receipts)
    assert calendar.last_month.received_cash == pytest.approx(2.50)
    assert calendar.current_month.received_cash == 0.0
