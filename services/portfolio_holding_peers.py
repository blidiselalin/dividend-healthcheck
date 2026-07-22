"""
Compare portfolio holdings that share the same sector (GICS / Yahoo labels).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from data_ingestion.sp500_universe import sectors_match

if TYPE_CHECKING:
    from models.stock import StockData
    from services.portfolio_analysis_preload import PortfolioAnalysisPreload
    from services.portfolio_details_service import PortfolioDetailRow


def _sym(symbol: str) -> str:
    return symbol.strip().upper()


def _clean_sector(value: str | None) -> str:
    if not value:
        return ""
    cleaned = str(value).strip()
    if cleaned.lower() in {"unknown", "n/a", ""}:
        return ""
    return cleaned


def lookup_stock_data(preload: PortfolioAnalysisPreload, symbol: str) -> StockData | None:
    sym = _sym(symbol)
    return preload.stock_data.get(sym) or preload.stock_data.get(symbol)


def lookup_vector_doc(preload: PortfolioAnalysisPreload, symbol: str) -> Any | None:
    sym = _sym(symbol)
    return preload.vector_docs.get(sym) or preload.vector_docs.get(symbol)


def resolve_holding_sector(
    symbol: str,
    row: PortfolioDetailRow,
    preload: PortfolioAnalysisPreload,
) -> str:
    """Sector label from the detail row, cached stock data, or library document."""
    stock = lookup_stock_data(preload, symbol)
    document = lookup_vector_doc(preload, symbol)
    for candidate in (
        row.sector,
        getattr(stock, "sector", None),
        getattr(document, "sector", None),
    ):
        label = _clean_sector(candidate)
        if label:
            return label
    return ""


def _load_stock_data(symbol: str, preload: PortfolioAnalysisPreload) -> StockData | None:
    data = lookup_stock_data(preload, symbol)
    if data is not None:
        return data
    document = lookup_vector_doc(preload, symbol)
    if document is None:
        return None
    from services.stock_analysis_service import load_portfolio_statistics_stock

    return load_portfolio_statistics_stock(_sym(symbol), document)


def build_peer_entry(
    row: PortfolioDetailRow,
    preload: PortfolioAnalysisPreload,
    *,
    stock_to_peer: Callable[[StockData], dict[str, Any]],
) -> dict[str, Any]:
    """Build a comparison row from analysis cache or portfolio detail fields."""
    data = _load_stock_data(row.ticker, preload)
    if data is not None:
        return stock_to_peer(data)
    return {
        "symbol": row.ticker,
        "name": row.company,
        "score": 0,
        "dividend_yield_pct": row.dividend_yield_pct,
        "trailing_pe": row.pe_ratio,
        "payout_ratio_pct": None,
        "roe_pct": None,
        "debt_to_equity": None,
        "div_streak": row.growth_years,
        "div_cagr": None,
        "dividend_tier": None,
    }


def collect_portfolio_sector_peers(
    symbol: str,
    row: PortfolioDetailRow,
    rows: list[PortfolioDetailRow],
    preload: PortfolioAnalysisPreload,
    *,
    stock_to_peer: Callable[[StockData], dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], StockData | None]:
    """
    Return (sector, peer_entries, current_stock_data) for same-sector holdings.

    Peers include other portfolio positions even when session preload lacks
    ``stock_data`` for them — sector is resolved from library documents when needed.
    """
    sector = resolve_holding_sector(symbol, row, preload)
    if not sector:
        return "", [], None

    current_data = _load_stock_data(symbol, preload)
    sym_upper = _sym(symbol)
    peers: list[dict[str, Any]] = []
    for other in rows:
        if _sym(other.ticker) == sym_upper:
            continue
        other_sector = resolve_holding_sector(other.ticker, other, preload)
        if not other_sector or not sectors_match(sector, other_sector):
            continue
        peers.append(build_peer_entry(other, preload, stock_to_peer=stock_to_peer))

    return sector, peers, current_data
