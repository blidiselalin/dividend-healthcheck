"""
Ensure every portfolio symbol exists in the vector DB with holdings metadata linked.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from config import DELISTED_SYMBOLS
from data_ingestion.models import DataSource, StockDocument
from services.portfolio_context import PortfolioContext, create_portfolio_context

logger = logging.getLogger(__name__)


def _company_name_for(symbol: str, ctx: PortfolioContext) -> Optional[str]:
    """Company name from the current user's holdings only."""
    symbol = symbol.upper()
    for holding in ctx.portfolio.list_holdings():
        if holding.symbol.upper() == symbol and holding.company_name:
            return holding.company_name
    return None


def collect_portfolio_symbols(ctx: Optional[PortfolioContext] = None) -> Set[str]:
    """All tickers from holdings and purchase journal."""
    context = ctx or create_portfolio_context()
    symbols: Set[str] = set()
    for holding in context.portfolio.list_holdings():
        symbols.add(holding.symbol.upper())
    for purchase in context.journal.list_purchases(portfolio_only=False):
        symbols.add(purchase.symbol.upper())
    return {symbol for symbol in symbols if symbol not in DELISTED_SYMBOLS}


def apply_portfolio_fields(
    document: StockDocument,
    *,
    holding: Optional[Any] = None,
    purchase_count: int = 0,
    company_name: Optional[str] = None,
) -> StockDocument:
    """Attach portfolio position data to a market library document."""
    document.in_portfolio = True
    document.last_updated = datetime.now()

    if company_name and (document.name == document.symbol or not document.name):
        document.name = company_name

    if holding is not None:
        document.portfolio_shares = float(holding.shares)
        document.portfolio_avg_cost_per_share = float(holding.avg_cost_per_share)
        document.portfolio_acquisition_value = float(holding.acquisition_value)
        document.portfolio_dividends_paid = float(holding.dividends_paid)
    else:
        document.portfolio_shares = None
        document.portfolio_avg_cost_per_share = None
        document.portfolio_acquisition_value = None
        document.portfolio_dividends_paid = None

    document.portfolio_purchase_count = purchase_count if purchase_count > 0 else None
    return document


def _purchase_counts(ctx: PortfolioContext) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for purchase in ctx.journal.list_purchases(portfolio_only=False):
        counts[purchase.symbol.upper()] += 1
    return dict(counts)


def _fetch_or_create_document(
    symbol: str,
    store: Any,
    ctx: PortfolioContext,
    *,
    enrich_missing: bool,
) -> Optional[StockDocument]:
    document = store.get_by_symbol(symbol)
    if document is not None:
        return document

    if not enrich_missing:
        return StockDocument(
            symbol=symbol,
            name=_company_name_for(symbol, ctx) or symbol,
            source=DataSource.MANUAL,
        )

    try:
        from data_ingestion.stock_enricher import create_stock_enricher

        document = create_stock_enricher(request_delay=0.35).fetch_document(symbol)
        if document is not None:
            return document
    except Exception as exc:
        logger.warning("Market data enrich failed for %s: %s", symbol, exc)

    return StockDocument(
        symbol=symbol,
        name=_company_name_for(symbol, ctx) or symbol,
        source=DataSource.MANUAL,
    )


def sync_portfolio_to_vector_db(
    *,
    enrich_missing: bool = True,
    symbols: Optional[List[str]] = None,
    db_path: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Link portfolio positions into the market library and create missing stock documents.

    Returns:
        Stats with linked, created, stored, still_missing, and errors counts.
    """
    from services.shared_market_db import get_shared_vector_store

    ctx = create_portfolio_context(db_path=db_path)
    target_symbols = sorted(
        symbol.upper()
        for symbol in (symbols or collect_portfolio_symbols(ctx))
        if symbol.upper() not in DELISTED_SYMBOLS
    )
    stats: Dict[str, Any] = {
        "symbols": target_symbols,
        "linked": 0,
        "created": 0,
        "stored": 0,
        "still_missing": [],
        "errors": 0,
        "timestamp": datetime.now().isoformat(),
    }

    if not target_symbols:
        return stats

    store = get_shared_vector_store()
    holdings_by_symbol = {
        holding.symbol.upper(): holding for holding in ctx.portfolio.list_holdings()
    }
    purchases = _purchase_counts(ctx)
    to_store: List[StockDocument] = []
    existing_ids = {
        document.symbol.upper()
        for document in store.get_all_documents()
        if document.symbol
    }

    for symbol in target_symbols:
        try:
            existed = symbol in existing_ids
            document = _fetch_or_create_document(
                symbol, store, ctx, enrich_missing=enrich_missing
            )
            if document is None:
                stats["still_missing"].append(symbol)
                continue
            if not existed:
                stats["created"] += 1
                existing_ids.add(symbol)

            apply_portfolio_fields(
                document,
                holding=holdings_by_symbol.get(symbol),
                purchase_count=purchases.get(symbol, 0),
                company_name=_company_name_for(symbol, ctx),
            )
            to_store.append(document)
            stats["linked"] += 1
        except Exception as exc:
            logger.error("Portfolio vector sync failed for %s: %s", symbol, exc)
            stats["errors"] += 1

    if to_store:
        store.add_documents(to_store)
        stats["stored"] = len(to_store)

    stats["total_documents"] = store.count()
    return stats


def link_portfolio_in_vector_db() -> Dict[str, Any]:
    """Fast path: update portfolio metadata only (no yfinance fetch)."""
    return sync_portfolio_to_vector_db(enrich_missing=False)
