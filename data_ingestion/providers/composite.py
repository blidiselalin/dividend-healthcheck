"""
Composite multi-source enricher.

Chains providers by priority; each provider fills only missing field groups.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from data_ingestion.models import StockDocument
from data_ingestion.providers.base import StockDataProvider
from data_ingestion.providers.sec_edgar import SecEdgarProvider
from data_ingestion.providers.snapshot import (
    FIELD_GROUPS,
    StockSnapshot,
    apply_snapshot_to_document,
    missing_field_groups,
)
from data_ingestion.providers.stooq import StooqProvider
from data_ingestion.providers.yahoo import YahooFinanceProvider
from data_ingestion.yfinance_enricher import YFinanceEnricher

logger = logging.getLogger(__name__)


def default_providers() -> list[StockDataProvider]:
    """Built-in providers sorted by priority (Yahoo → SEC EDGAR → Stooq). All free, no API keys."""
    providers: list[StockDataProvider] = [
        YahooFinanceProvider(request_delay=0.35),
        SecEdgarProvider(request_delay=0.2),
        StooqProvider(request_delay=0.2),
    ]
    return sorted(providers, key=lambda provider: provider.priority)


class MultiSourceEnricher:
    """
    Enrich ``StockDocument`` from multiple vendors.

    Strategy:
    1. Start from existing document fields.
    2. For each provider (by priority), skip if no overlapping missing groups.
    3. Merge snapshot gaps only — never overwrite populated scalars.
    4. Optionally delegate heavy history/streak math to ``YFinanceEnricher``.
    """

    def __init__(
        self,
        providers: Sequence[StockDataProvider] | None = None,
        *,
        use_yfinance_post_process: bool = True,
        request_delay: float = 0.35,
    ) -> None:
        self.providers = list(providers) if providers is not None else default_providers()
        self.use_yfinance_post_process = use_yfinance_post_process
        self._legacy = YFinanceEnricher(request_delay=request_delay)

    def fetch_snapshot(self, symbol: str, *, doc: StockDocument | None = None) -> StockSnapshot:
        """Fetch merged snapshot for ``symbol``, optionally respecting existing doc gaps."""
        symbol = symbol.upper().strip()
        merged = StockSnapshot(symbol=symbol)
        missing = set(missing_field_groups(doc)) if doc else set(FIELD_GROUPS.keys())

        for provider in self.providers:
            if not provider.available():
                continue
            if missing and not provider.supports_groups(missing):
                continue
            snap = provider.fetch(symbol)
            if snap is None:
                continue
            merged.merge_from(snap)
            if doc is not None:
                probe = _probe_document(doc, merged)
                missing = set(missing_field_groups(probe))
                if not missing:
                    break
        return merged

    def enrich_document(self, doc: StockDocument) -> StockDocument:
        """Fill gaps on ``doc`` using all configured providers."""
        before_groups = missing_field_groups(doc)
        merged = self.fetch_snapshot(doc.symbol, doc=doc)
        doc = apply_snapshot_to_document(doc, merged)

        if self.use_yfinance_post_process:
            # Reuse streak/CAGR/history calculations from the legacy enricher.
            doc = self._legacy.enrich_document(doc)

        after_groups = missing_field_groups(doc)
        filled = set(before_groups) - set(after_groups)
        if filled:
            logger.info(
                "%s: multi-source fill groups=%s sources=%s",
                doc.symbol,
                sorted(filled),
                merged.source.value,
            )
        return doc

    def enrich_batch(
        self,
        documents: list[StockDocument],
        progress_callback: Any | None = None,
    ) -> list[StockDocument]:
        enriched: list[StockDocument] = []
        total = len(documents)
        for index, doc in enumerate(documents):
            enriched.append(self.enrich_document(doc))
            if progress_callback:
                progress_callback(index + 1, total)
        return enriched

    def fetch_document(self, symbol: str) -> StockDocument | None:
        """Create a new document from merged provider data."""
        from data_ingestion.models import DataSource

        snap = self.fetch_snapshot(symbol)
        if not snap.populated_scalar_fields() and not snap.dividend_history:
            return None
        doc = StockDocument(
            symbol=symbol.upper(),
            name=snap.name or symbol.upper(),
            source=DataSource.MANUAL,
        )
        doc = apply_snapshot_to_document(doc, snap)
        if self.use_yfinance_post_process:
            doc = self._legacy.enrich_document(doc)
        return doc


def _probe_document(doc: StockDocument, merged: StockSnapshot) -> StockDocument:
    """Apply merged snapshot onto a copy to detect remaining gaps."""
    import copy

    probe = copy.deepcopy(doc)
    return apply_snapshot_to_document(probe, merged)
