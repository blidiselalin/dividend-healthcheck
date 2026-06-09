"""Tests for portfolio dividend growth aggregation."""

from __future__ import annotations

from datetime import date

from data_ingestion.models import DataSource, DividendRecord, StockDocument
from services.portfolio_dividend_growth_service import (
    PortfolioDividendGrowthService,
    SymbolDividendGrowth,
)


def test_consecutive_growth_years():
    annual = {2021: 1.0, 2022: 1.1, 2023: 1.2, 2024: 1.3}
    assert PortfolioDividendGrowthService._consecutive_growth_years(annual) == 3


def test_cagr_requires_positive_values():
    assert PortfolioDividendGrowthService._cagr({2021: 1.0, 2022: 1.2}) == 20.0
    assert PortfolioDividendGrowthService._cagr({2021: 0.0, 2022: 1.0}) is None
    assert PortfolioDividendGrowthService._cagr({2021: 1.0}) is None


def test_annual_dividends_estimates_current_year(monkeypatch):
    monkeypatch.setattr(
        "services.portfolio_dividend_growth_service.date",
        type(
            "date",
            (),
            {"today": staticmethod(lambda: date(2025, 5, 19))},
        ),
    )
    doc = StockDocument(symbol="KO", name="Coca-Cola", source=DataSource.YAHOO)
    doc.annual_dividend = 2.0
    records = [
        DividendRecord(ex_date=date(2024, 2, 1), payment_date=None, amount=0.5),
        DividendRecord(ex_date=date(2024, 5, 1), payment_date=None, amount=0.5),
        DividendRecord(ex_date=date(2025, 2, 1), payment_date=None, amount=0.52),
    ]
    service = PortfolioDividendGrowthService(portfolio_store=MagicMockPortfolio())
    annual = service._annual_dividends_from_history(
        records,
        since_year=2024,
        document=doc,
    )
    assert annual[2024] == 1.0
    assert annual[2025] == 2.0


def test_portfolio_cash_by_year():
    items = [
        SymbolDividendGrowth(
            symbol="KO",
            company="Coca-Cola",
            annual_by_year={2023: 1.0, 2024: 1.1},
            growth_years=1,
            cagr_since_start=10.0,
            latest_annual=1.1,
            shares=100.0,
        )
    ]
    service = PortfolioDividendGrowthService(portfolio_store=MagicMockPortfolio())
    cash = service.portfolio_cash_by_year(items)
    assert cash.loc[cash["Year"] == "2024", "Est. dividends $"].iloc[0] == 110.0
    assert cash.loc[cash["Year"] == "2023", "Est. dividends $"].iloc[0] == 100.0


def test_yoy_growth_matrix_first_year_is_blank():
    items = [
        SymbolDividendGrowth(
            symbol="KO",
            company="Coca-Cola",
            annual_by_year={2023: 1.0, 2024: 1.1},
            growth_years=1,
            cagr_since_start=10.0,
            latest_annual=1.1,
            shares=10.0,
        )
    ]
    service = PortfolioDividendGrowthService(portfolio_store=MagicMockPortfolio())
    matrix = service.yoy_growth_matrix(items)
    assert matrix.loc[0, "2023"] is None
    assert matrix.loc[0, "2024"] == 10.0


class MagicMockPortfolio:
    def list_holdings(self):
        return []
