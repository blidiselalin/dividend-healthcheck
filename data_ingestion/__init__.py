"""
Data ingestion module for external stock data sources.

This module handles downloading, processing, and storing stock market data
from public sources into a vector database for enhanced report generation.

Fetchers:
- StockQuoteFetcher: Downloads dividend lists and fundamentals
- NasdaqFetcher: Downloads from Nasdaq.com (historical prices, dividend history)

Parsers:
- StockQuoteDownloader: Parses StockQuote.io CSV files
- NasdaqDownloader: Parses Nasdaq CSV/JSON files
"""

from .base import BaseFetcher
from .downloaders import NasdaqDownloader, StockQuoteDownloader
from .models import DividendRecord, PriceHistory, StockDocument
from .pipeline import DataIngestionPipeline
from .vector_store import VectorStore

__all__ = [
    "BaseFetcher",
    "DataIngestionPipeline",
    "DividendRecord",
    "NasdaqDownloader",
    "PriceHistory",
    "StockDocument",
    "StockQuoteDownloader",
    "VectorStore",
]

# Optional fetchers (require requests library)
try:
    from .fetch_nasdaq import NasdaqFetcher  # noqa: F401
    from .fetch_stockquote import StockQuoteFetcher  # noqa: F401

    __all__.extend(["NasdaqFetcher", "StockQuoteFetcher"])
except ImportError:
    pass
