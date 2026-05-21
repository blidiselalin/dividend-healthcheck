"""
Ensure every portfolio symbol exists in the vector DB with holdings metadata linked.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from config import DELISTED_SYMBOLS, VECTORDB_DIR
from data_ingestion.models import DataSource, StockDocument
from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore

logger = logging.getLogger(__name__)


def _company_name_for(symbol: str) -> Optional[str]:
    """Company name from the current user's holdings only."""
    symbol = symbol.upper()
    for holding in PortfolioStore(seed=False).list_holdings():
        if holding.symbol.upper() == symbol and holding.company_name:
            return holding.company_name
    return None


def collect_portfolio_symbols() -> Set[str]:
    """All tickers from holdings and purchase journal."""
    symbols: Set[str] = set()
    for holding in PortfolioStore(seed=False).list_holdings():
        symbols.add(holding.symbol.upper())
    for purchase in PurchaseJournalStore().list_purchases(portfolio_only=False):
        symbols.add(purchase.symbol.upper())
    return {symbol for symbol in symbols if symbol not in DELISTED_SYMBOLS}


def apply_portfolio_fields(
    document: StockDocument,
    *,
    holding: Optional[Any] = None,
    purchase_count: int = 0,
    company_name: Optional[str] = None,
) -> StockDocument:
    """Attach SQLite portfolio position data to a vector document."""
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


def _purchase_counts() -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for purchase in PurchaseJournalStore().list_purchases(portfolio_only=False):
        counts[purchase.symbol.upper()] += 1
    return dict(counts)


def _fetch_or_create_document(
    symbol: str,
    store: Any,
    *,
    enrich_missing: bool,
) -> Optional[StockDocument]:
    document = store.get_by_symbol(symbol)
    if document is not None:
        return document

    if not enrich_missing:
        return StockDocument(
            symbol=symbol,
            name=_company_name_for(symbol) or symbol,
            source=DataSource.MANUAL,
        )

    try:
        from data_ingestion.yfinance_enricher import YFinanceEnricher

        enricher = YFinanceEnricher(request_delay=0.35)
        document = enricher.fetch_document(symbol)
        if document is not None:
            document.source = DataSource.YAHOO
        return document
    except Exception as exc:
        logger.warning("Could not enrich %s for vector DB: %s", symbol, exc)
        return StockDocument(
            symbol=symbol,
            name=_company_name_for(symbol) or symbol,
            source=DataSource.MANUAL,
        )


def sync_portfolio_to_vector_db(
    *,
    enrich_missing: bool = True,
    symbols: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Link portfolio.db positions into the vector DB and create missing stock documents.

    Returns:
        Stats with linked, created, stored, still_missing, and errors counts.
    """
    from data_ingestion.vector_store import VectorStore

    target_symbols = sorted(
        symbol.upper()
        for symbol in (symbols or collect_portfolio_symbols())
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

    store = VectorStore(persist_directory=str(VECTORDB_DIR))
    holdings_by_symbol = {
        holding.symbol.upper(): holding
        for holding in PortfolioStore(seed=False).list_holdings()
    }
    purchases = _purchase_counts()
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
                symbol, store, enrich_missing=enrich_missing
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
                company_name=_company_name_for(symbol),
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
