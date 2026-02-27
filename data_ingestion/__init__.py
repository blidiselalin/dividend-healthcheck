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
from .models import StockDocument, DividendRecord, PriceHistory
from .vector_store import VectorStore
from .downloaders import StockQuoteDownloader, NasdaqDownloader
from .pipeline import DataIngestionPipeline

__all__ = [
    "BaseFetcher",
    "StockDocument",
    "DividendRecord",
    "PriceHistory",
    "VectorStore",
    "StockQuoteDownloader",
    "NasdaqDownloader",
    "DataIngestionPipeline",
]

# Optional fetchers (require requests library)
try:
    from .fetch_stockquote import StockQuoteFetcher
    from .fetch_nasdaq import NasdaqFetcher
    __all__.extend(["StockQuoteFetcher", "NasdaqFetcher"])
except ImportError:
    pass
