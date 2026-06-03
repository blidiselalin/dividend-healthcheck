"""
Single entry point for enriching ``StockDocument`` from external market data.

Uses ``MultiSourceEnricher``: Yahoo Finance → SEC EDGAR → Stooq (all free, no API keys).
"""

from __future__ import annotations

from typing import Any, Dict, List

try:
    from data_ingestion.providers.composite import MultiSourceEnricher, default_providers

    ENRICHER_AVAILABLE = True
except ImportError:
    ENRICHER_AVAILABLE = False
    MultiSourceEnricher = None  # type: ignore[misc, assignment]


def create_stock_enricher(request_delay: float = 0.35) -> "MultiSourceEnricher":
    """Return the shared multi-source enricher (Yahoo + SEC + Stooq)."""
    if not ENRICHER_AVAILABLE:
        raise RuntimeError("Stock enricher dependencies are not installed")
    return MultiSourceEnricher(request_delay=request_delay)


def provider_status() -> List[Dict[str, Any]]:
    """Report which market-data providers are active (all should be on when deps exist)."""
    if not ENRICHER_AVAILABLE:
        return []

    rows: List[Dict[str, Any]] = []
    for provider in default_providers():
        rows.append(
            {
                "id": provider.source.value,
                "priority": provider.priority,
                "available": provider.available(),
                "field_groups": sorted(provider.field_groups),
            }
        )
    return rows


def log_provider_status(logger) -> None:
    """Log configured market data providers at INFO level."""
    for row in provider_status():
        state = "on" if row["available"] else "off"
        logger.info(
            "Market data provider %s: %s — groups=%s",
            row["id"],
            state,
            ",".join(row["field_groups"]),
        )
