"""
Ensure every portfolio symbol exists in the vector DB with holdings metadata linked.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Any, cast

import requests

from config import DELISTED_SYMBOLS
from data_ingestion.models import DataSource, StockDocument
from services.portfolio_context import PortfolioContext, create_portfolio_context

logger = logging.getLogger(__name__)


def _company_name_for(symbol: str, ctx: PortfolioContext) -> str | None:
    """Company name from the current user's holdings only."""
    symbol = symbol.upper()
    for holding in ctx.portfolio.list_holdings():
        if holding.symbol.upper() == symbol and holding.company_name:
            return holding.company_name
    return None


def collect_portfolio_symbols(
    ctx: PortfolioContext | None = None,
    *,
    include_journal_history: bool = False,
) -> set[str]:
    """Tickers with open holdings; optionally include journal-only history symbols."""
    context = ctx or create_portfolio_context()
    symbols: set[str] = set()
    for holding in context.portfolio.list_holdings():
        if holding.shares > 0:
            symbols.add(holding.symbol.upper())
    if include_journal_history:
        for purchase in context.journal.list_purchases(portfolio_only=False):
            symbols.add(purchase.symbol.upper())
    return {symbol for symbol in symbols if symbol not in DELISTED_SYMBOLS}


def apply_portfolio_fields(
    document: StockDocument,
    *,
    holding: Any | None = None,
    purchase_count: int = 0,
    company_name: str | None = None,
    touch_library_timestamp: bool = True,
) -> StockDocument:
    """Attach portfolio position data to a market library document."""
    document.in_portfolio = holding is not None
    if touch_library_timestamp:
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


def _purchase_counts(ctx: PortfolioContext) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for purchase in ctx.journal.list_purchases(portfolio_only=False):
        counts[purchase.symbol.upper()] += 1
    return dict(counts)


def _should_full_library_store(
    document: StockDocument, *, existed: bool, enrich_missing: bool
) -> bool:
    """Full ingest (with history dual-write) only for newly enriched library documents."""
    if existed or not enrich_missing:
        return False
    return bool(
        document.price_history or document.dividend_history or document.current_price is not None
    )


def _fetch_or_create_document(
    symbol: str,
    store: Any,
    ctx: PortfolioContext,
    *,
    enrich_missing: bool,
) -> StockDocument | None:
    document = store.get_by_symbol(symbol)
    if document is not None:
        return cast(StockDocument, document)

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
            return cast(StockDocument, document)
    except Exception as exc:
        logger.warning("Market data enrich failed for %s: %s", symbol, exc)  # noqa: BLE001

    return StockDocument(
        symbol=symbol,
        name=_company_name_for(symbol, ctx) or symbol,
        source=DataSource.MANUAL,
    )


def sync_portfolio_to_vector_db(
    *,
    enrich_missing: bool = True,
    symbols: list[str] | None = None,
    db_path: Any | None = None,
) -> dict[str, Any]:
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
    stats: dict[str, Any] = {
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
    to_patch: list[StockDocument] = []
    to_store_full: list[StockDocument] = []
    existing_ids = {
        document.symbol.upper() for document in store.get_all_documents() if document.symbol
    }

    for symbol in target_symbols:
        try:
            existed = symbol in existing_ids
            document = _fetch_or_create_document(symbol, store, ctx, enrich_missing=enrich_missing)
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
                touch_library_timestamp=False,
            )
            if _should_full_library_store(document, existed=existed, enrich_missing=enrich_missing):
                to_store_full.append(document)
            else:
                to_patch.append(document)
            stats["linked"] += 1
        except requests.exceptions.RequestException as exc:
            logger.error("Portfolio vector sync failed for %s: %s", symbol, exc)
            stats["errors"] += 1

    if hasattr(store, "patch_portfolio_metadata") and to_patch:
        store.patch_portfolio_metadata(to_patch)
        stats["stored"] += len(to_patch)
    elif to_patch:
        store.add_documents(to_patch)
        stats["stored"] += len(to_patch)

    if to_store_full:
        store.add_documents(to_store_full)
        stats["stored"] += len(to_store_full)

    stats["total_documents"] = store.count()
    return stats


def link_portfolio_in_vector_db() -> dict[str, Any]:
    """Fast path: update portfolio metadata only (no yfinance fetch)."""
    return sync_portfolio_to_vector_db(enrich_missing=False)
