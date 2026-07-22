"""Tests for same-sector portfolio holding comparison."""

from __future__ import annotations

from unittest.mock import MagicMock

from data_ingestion.models import StockDocument
from services.portfolio_analysis_preload import PortfolioAnalysisPreload
from services.portfolio_details_service import PortfolioDetailRow
from services.portfolio_holding_peers import (
    collect_portfolio_sector_peers,
    resolve_holding_sector,
)


def _row(
    ticker: str,
    *,
    sector: str = "Unknown",
    company: str | None = None,
) -> PortfolioDetailRow:
    return PortfolioDetailRow(
        company=company or ticker,
        ticker=ticker,
        market_cap=None,
        pe_ratio=20.0,
        shares=10.0,
        current_price=100.0,
        current_value=1000.0,
        avg_cost_per_share=90.0,
        acquisition_value=900.0,
        profit=100.0,
        profit_pct=11.1,
        estimated_avg_price=90.0,
        medium_price_365d=None,
        price_180d=None,
        price_365d=None,
        change_180d_pct=None,
        change_365d_pct=None,
        weight_pct=10.0,
        dividend_yield_pct=3.0,
        dividend_per_share=3.0,
        annual_income=30.0,
        dividend_weight_pct=10.0,
        income_weight_pct=10.0,
        dividends_paid=0.0,
        growth_years=5,
        commission=0.0,
        sector=sector,
        acquisition_share_pct=None,
        analyst_rating="hold",
        price_to_fcf=None,
        computed_dividend="3.0",
        ex_dividend_date=None,
        dividend_pay_date=None,
        data_source="test",
    )


def test_resolve_holding_sector_from_vector_doc_when_row_unknown() -> None:
    row = _row("O", sector="Unknown")
    doc = StockDocument(symbol="O", name="Realty Income", sector="Real Estate")
    preload = PortfolioAnalysisPreload.from_caches(vector_docs={"O": doc})

    assert resolve_holding_sector("O", row, preload) == "Real Estate"


def test_collect_peers_when_only_library_sector_available() -> None:
    row_a = _row("O", sector="Unknown")
    row_n = _row("NNN", sector="Unknown")
    doc_o = StockDocument(symbol="O", name="Realty Income", sector="Real Estate")
    doc_n = StockDocument(symbol="NNN", name="NNN REIT", sector="Real Estate")
    preload = PortfolioAnalysisPreload.from_caches(
        vector_docs={"O": doc_o, "NNN": doc_n},
    )

    def _peer(data: MagicMock) -> dict[str, object]:
        return {"symbol": data.symbol, "name": data.name, "score": 50}

    sector, peers, current = collect_portfolio_sector_peers(
        "O",
        row_a,
        [row_a, row_n],
        preload,
        stock_to_peer=_peer,
    )

    assert sector == "Real Estate"
    assert current is not None
    assert current.symbol == "O"
    assert len(peers) == 1
    assert peers[0]["symbol"] == "NNN"


def test_collect_peers_uses_row_sector_without_stock_data() -> None:
    row_ko = _row("KO", sector="Consumer Defensive")
    row_pep = _row("PEP", sector="Consumer Staples")
    preload = PortfolioAnalysisPreload.from_caches()

    sector, peers, _current = collect_portfolio_sector_peers(
        "KO",
        row_ko,
        [row_ko, row_pep],
        preload,
        stock_to_peer=lambda data: {"symbol": data.symbol, "score": 1},
    )

    assert sector == "Consumer Defensive"
    assert len(peers) == 1
    assert peers[0]["symbol"] == "PEP"
    assert peers[0]["score"] == 0
