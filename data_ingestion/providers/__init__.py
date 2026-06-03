"""
Multi-source stock data providers (free sources only in the default chain).

Yahoo → SEC EDGAR → Stooq. See ``data_ingestion.stock_enricher``.
"""

from data_ingestion.providers.composite import MultiSourceEnricher, default_providers
from data_ingestion.providers.snapshot import StockSnapshot, missing_field_groups

__all__ = [
    "MultiSourceEnricher",
    "StockSnapshot",
    "default_providers",
    "missing_field_groups",
]
