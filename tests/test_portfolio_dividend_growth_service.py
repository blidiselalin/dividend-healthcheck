"""Tests for portfolio dividend growth aggregation."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from data_ingestion.models import DataSource, DividendRecord, StockDocument
from data_ingestion.portfolio_store import PortfolioHolding
from data_ingestion.purchase_journal_store import PurchaseRecord
from services.portfolio_dividend_growth_service import (
    PortfolioDividendGrowthService,
    SymbolDividendGrowth,
)

# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


class MagicMockPortfolio:
    def list_holdings(self) -> list[Any]:
        return []


class _MockJournal:
    """Stub purchase-journal that returns a fixed list of PurchaseRecord."""

    def __init__(self, records: list[PurchaseRecord]) -> None:
        self._records = records

    def list_purchases(self, portfolio_only: bool = True) -> list[PurchaseRecord]:
        return self._records


class _MockVectorStore:
    """Stub vector store backed by a dict of symbol → StockDocument."""

    def __init__(self, docs: dict[str, StockDocument]) -> None:
        self._docs = {k.upper(): v for k, v in docs.items()}

    def get_by_symbol(self, symbol: str) -> StockDocument | None:
        return self._docs.get(symbol.upper())

    def get_by_symbols(self, symbols: list[str]) -> dict[str, Any]:
        return {s.upper(): doc for s in symbols if (doc := self._docs.get(s.upper())) is not None}


def _make_holding(
    symbol: str,
    shares: float = 10.0,
    tracking_since: date | None = None,
) -> PortfolioHolding:
    return PortfolioHolding(
        symbol=symbol,
        shares=shares,
        avg_cost_per_share=50.0,
        acquisition_value=shares * 50.0,
        commission=0.0,
        dividends_paid=0.0,
        estimated_avg_price=50.0,
        sort_order=0,
        company_name=None,
        dividend_tracking_since=tracking_since,
    )


def _make_doc(symbol: str, records: list[DividendRecord]) -> StockDocument:
    doc = StockDocument(symbol=symbol, name=symbol, source=DataSource.YAHOO)
    doc.dividend_history = records
    doc.annual_dividend = sum(r.amount for r in records[-4:] if r.amount)
    return doc


# ---------------------------------------------------------------------------
# Existing tests (unchanged)
# ---------------------------------------------------------------------------


def test_consecutive_growth_years() -> None:
    annual = {2021: 1.0, 2022: 1.1, 2023: 1.2, 2024: 1.3}
    assert PortfolioDividendGrowthService._consecutive_growth_years(annual) == 3


def test_cagr_requires_positive_values() -> None:
    assert PortfolioDividendGrowthService._cagr({2021: 1.0, 2022: 1.2}) == 20.0
    assert PortfolioDividendGrowthService._cagr({2021: 0.0, 2022: 1.0}) is None
    assert PortfolioDividendGrowthService._cagr({2021: 1.0}) is None


def test_annual_dividends_estimates_current_year(monkeypatch: pytest.MonkeyPatch) -> None:
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
    service = PortfolioDividendGrowthService(portfolio_store=MagicMockPortfolio())  # type: ignore[arg-type]
    annual = service._annual_dividends_from_history(
        records,
        since_year=2024,
        document=doc,
    )
    assert annual[2024] == 1.0
    assert annual[2025] == 2.0


def test_portfolio_cash_by_year() -> None:
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
    service = PortfolioDividendGrowthService(portfolio_store=MagicMockPortfolio())  # type: ignore[arg-type]
    cash = service.portfolio_cash_by_year(items)
    assert cash.loc[cash["Year"] == "2024", "Est. dividends $"].iloc[0] == 110.0
    assert cash.loc[cash["Year"] == "2023", "Est. dividends $"].iloc[0] == 100.0


def test_yoy_growth_matrix_first_year_is_blank() -> None:
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
    service = PortfolioDividendGrowthService(portfolio_store=MagicMockPortfolio())  # type: ignore[arg-type]
    matrix = service.yoy_growth_matrix(items)
    assert matrix.loc[0, "2023"] is None
    assert matrix.loc[0, "2024"] == 10.0


def test_annual_matrix_uses_plain_year_columns() -> None:
    items = [
        SymbolDividendGrowth(
            symbol="KO",
            company="Coca-Cola",
            annual_by_year={2025: 2.0},
            growth_years=0,
            cagr_since_start=None,
            latest_annual=2.0,
            shares=10.0,
        )
    ]
    service = PortfolioDividendGrowthService(portfolio_store=MagicMockPortfolio())  # type: ignore[arg-type]
    matrix = service.annual_matrix_dataframe(items)
    assert "2025" in matrix.columns
    assert "2025 (est.)" not in matrix.columns


# ---------------------------------------------------------------------------
# New tests: pre-ownership filtering
# ---------------------------------------------------------------------------


def test_portfolio_cash_skips_years_before_first_owned() -> None:
    """Cash chart must exclude years before the user owned the stock."""
    items = [
        SymbolDividendGrowth(
            symbol="KO",
            company="Coca-Cola",
            annual_by_year={2021: 1.0, 2022: 1.1, 2023: 1.2, 2024: 1.3},
            growth_years=3,
            cagr_since_start=9.1,
            latest_annual=1.3,
            shares=100.0,
            first_owned_year=2023,  # bought in 2023 — 2021/2022 must be excluded
        )
    ]
    service = PortfolioDividendGrowthService(portfolio_store=MagicMockPortfolio())  # type: ignore[arg-type]
    cash = service.portfolio_cash_by_year(items)

    years = set(cash["Year"].tolist())
    assert "2021" not in years
    assert "2022" not in years
    assert "2023" in years
    assert "2024" in years
    assert cash.loc[cash["Year"] == "2023", "Est. dividends $"].iloc[0] == 120.0
    assert cash.loc[cash["Year"] == "2024", "Est. dividends $"].iloc[0] == 130.0


def test_portfolio_cash_no_filter_when_first_owned_year_is_none() -> None:
    """When first_owned_year is None all years are included (legacy behaviour)."""
    items = [
        SymbolDividendGrowth(
            symbol="KO",
            company="Coca-Cola",
            annual_by_year={2021: 1.0, 2022: 1.1},
            growth_years=1,
            cagr_since_start=10.0,
            latest_annual=1.1,
            shares=10.0,
            first_owned_year=None,
        )
    ]
    service = PortfolioDividendGrowthService(portfolio_store=MagicMockPortfolio())  # type: ignore[arg-type]
    cash = service.portfolio_cash_by_year(items)
    assert set(cash["Year"].tolist()) == {"2021", "2022"}


def test_portfolio_cash_multi_symbol_partial_ownership() -> None:
    """Two holdings with different start years; each filters independently."""
    items = [
        SymbolDividendGrowth(
            symbol="AAPL",
            company="Apple",
            annual_by_year={2021: 0.8, 2022: 0.9, 2023: 1.0},
            growth_years=2,
            cagr_since_start=11.8,
            latest_annual=1.0,
            shares=50.0,
            first_owned_year=2022,  # owned from 2022
        ),
        SymbolDividendGrowth(
            symbol="KO",
            company="Coca-Cola",
            annual_by_year={2021: 1.0, 2022: 1.1, 2023: 1.2},
            growth_years=2,
            cagr_since_start=9.5,
            latest_annual=1.2,
            shares=100.0,
            first_owned_year=2021,  # owned from 2021
        ),
    ]
    service = PortfolioDividendGrowthService(portfolio_store=MagicMockPortfolio())  # type: ignore[arg-type]
    cash = service.portfolio_cash_by_year(items)

    # 2021: only KO contributes (AAPL excluded because first_owned_year=2022)
    row_2021 = cash.loc[cash["Year"] == "2021", "Est. dividends $"].iloc[0]
    assert row_2021 == pytest.approx(1.0 * 100.0)  # KO only

    # 2022: both contribute
    row_2022 = cash.loc[cash["Year"] == "2022", "Est. dividends $"].iloc[0]
    assert row_2022 == pytest.approx(0.9 * 50.0 + 1.1 * 100.0)

    # 2023: both contribute
    row_2023 = cash.loc[cash["Year"] == "2023", "Est. dividends $"].iloc[0]
    assert row_2023 == pytest.approx(1.0 * 50.0 + 1.2 * 100.0)


# ---------------------------------------------------------------------------
# New tests: first_owned_year populated in build_symbol_growth
# ---------------------------------------------------------------------------


class _MockPortfolio:
    def __init__(self, holdings: list[PortfolioHolding]) -> None:
        self._holdings = holdings

    def list_holdings(self) -> list[PortfolioHolding]:
        return self._holdings

    def list_open_holdings(self) -> list[PortfolioHolding]:
        return [holding for holding in self._holdings if holding.shares > 0]


def test_build_symbol_growth_uses_journal_for_first_owned_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """first_owned_year is taken from the earliest purchase in the journal."""
    records = [
        DividendRecord(ex_date=date(2021, 3, 1), payment_date=None, amount=0.44),
        DividendRecord(ex_date=date(2022, 3, 1), payment_date=None, amount=0.46),
        DividendRecord(ex_date=date(2023, 3, 1), payment_date=None, amount=0.48),
    ]
    doc = _make_doc("KO", records)

    purchases = [
        PurchaseRecord(symbol="KO", purchase_date=date(2022, 6, 1), price_usd=55.0, id=1),
        PurchaseRecord(symbol="KO", purchase_date=date(2023, 1, 15), price_usd=58.0, id=2),
    ]
    journal = _MockJournal(purchases)
    portfolio = _MockPortfolio([_make_holding("KO", shares=10.0)])
    vector_store = _MockVectorStore({"KO": doc})
    _patch_resolve_docs(monkeypatch, {"KO": doc})

    service = PortfolioDividendGrowthService(
        vector_store=vector_store,
        portfolio_store=portfolio,  # type: ignore[arg-type]
        journal_store=journal,  # type: ignore[arg-type]
    )
    results = service.build_symbol_growth(since_year=2021)

    assert len(results) == 1
    assert results[0].first_owned_year == 2022  # earliest purchase year


def _patch_resolve_docs(monkeypatch: pytest.MonkeyPatch, docs: dict[str, StockDocument]) -> None:
    normalized = {symbol.strip().upper(): doc for symbol, doc in docs.items()}

    def _fake(
        holdings: list[PortfolioHolding],
        preload: Any | None = None,
        *,
        fetch_remote: bool = False,
    ) -> tuple[dict[str, StockDocument], dict[str, Any]]:
        del preload, fetch_remote
        return dict(normalized), {}

    monkeypatch.setattr(
        "services.portfolio_dividend_cash.resolve_dividend_documents",
        _fake,
    )


def test_build_symbol_growth_falls_back_to_tracking_since(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When journal is empty, first_owned_year falls back to dividend_tracking_since."""
    records = [
        DividendRecord(ex_date=date(2021, 3, 1), payment_date=None, amount=0.44),
        DividendRecord(ex_date=date(2022, 3, 1), payment_date=None, amount=0.46),
    ]
    doc = _make_doc("MSFT", records)

    journal = _MockJournal([])  # no journal entries
    holding = _make_holding("MSFT", shares=5.0, tracking_since=date(2022, 4, 1))
    portfolio = _MockPortfolio([holding])
    vector_store = _MockVectorStore({"MSFT": doc})
    _patch_resolve_docs(monkeypatch, {"MSFT": doc})

    service = PortfolioDividendGrowthService(
        vector_store=vector_store,
        portfolio_store=portfolio,  # type: ignore[arg-type]
        journal_store=journal,  # type: ignore[arg-type]
    )
    results = service.build_symbol_growth(since_year=2021)

    assert len(results) == 1
    assert results[0].first_owned_year == 2022


def test_build_symbol_growth_no_filter_when_no_tracking_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """first_owned_year is None when neither journal nor tracking_since is available."""
    records = [
        DividendRecord(ex_date=date(2021, 3, 1), payment_date=None, amount=0.44),
        DividendRecord(ex_date=date(2022, 3, 1), payment_date=None, amount=0.46),
    ]
    doc = _make_doc("T", records)

    journal = _MockJournal([])
    holding = _make_holding("T", shares=20.0, tracking_since=None)
    portfolio = _MockPortfolio([holding])
    vector_store = _MockVectorStore({"T": doc})
    _patch_resolve_docs(monkeypatch, {"T": doc})

    service = PortfolioDividendGrowthService(
        vector_store=vector_store,
        portfolio_store=portfolio,  # type: ignore[arg-type]
        journal_store=journal,  # type: ignore[arg-type]
    )
    results = service.build_symbol_growth(since_year=2021)

    assert len(results) == 1
    assert results[0].first_owned_year is None


# ---------------------------------------------------------------------------
# New tests: batch document fetch (VectorStore.get_by_symbols)
# ---------------------------------------------------------------------------


def test_vector_store_get_by_symbols_returns_all_found(tmp_path: Any) -> None:
    """get_by_symbols on the mock returns only symbols that exist."""
    records = [DividendRecord(ex_date=date(2023, 3, 1), payment_date=None, amount=0.5)]
    docs = {
        "AAPL": _make_doc("AAPL", records),
        "KO": _make_doc("KO", records),
    }
    store = _MockVectorStore(docs)

    result = store.get_by_symbols(["AAPL", "KO", "MSFT"])

    assert set(result.keys()) == {"AAPL", "KO"}
    assert result["AAPL"].symbol == "AAPL"
    assert result["KO"].symbol == "KO"


def test_vector_store_get_by_symbols_empty_input() -> None:
    store = _MockVectorStore({})
    assert store.get_by_symbols([]) == {}


def test_build_symbol_growth_uses_resolved_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    """build_symbol_growth loads dividend history via resolve_dividend_documents."""
    records = [
        DividendRecord(ex_date=date(2023, 3, 1), payment_date=None, amount=0.44),
        DividendRecord(ex_date=date(2024, 3, 1), payment_date=None, amount=0.46),
    ]
    docs = {
        "KO": _make_doc("KO", records),
        "AAPL": _make_doc("AAPL", records),
    }
    portfolio = _MockPortfolio(
        [_make_holding("KO", shares=10.0), _make_holding("AAPL", shares=5.0)]
    )
    journal = _MockJournal([])

    resolve_calls: list[int] = []

    def _fake(
        holdings: list[PortfolioHolding],
        preload: Any | None = None,
        *,
        fetch_remote: bool = False,
    ) -> tuple[dict[str, StockDocument], dict[str, Any]]:
        del preload, fetch_remote
        resolve_calls.append(len(holdings))
        return docs, {}

    monkeypatch.setattr(
        "services.portfolio_dividend_cash.resolve_dividend_documents",
        _fake,
    )

    service = PortfolioDividendGrowthService(
        vector_store=_MockVectorStore({}),
        portfolio_store=portfolio,  # type: ignore[arg-type]
        journal_store=journal,  # type: ignore[arg-type]
    )
    results = service.build_symbol_growth(since_year=2023)

    assert resolve_calls == [2]
    assert len(results) == 2
