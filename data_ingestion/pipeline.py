"""
Data ingestion pipeline for processing stock data into vector DB.

This pipeline orchestrates the download, parsing, merging, and storage
of stock data from multiple public sources.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from .models import StockDocument, DataSource
from .downloaders import StockQuoteDownloader, NasdaqDownloader, BaseDownloader
from .vector_store import VectorStore

# Import config for default paths
try:
    from config import DOWNLOADS_DIR, VECTORDB_DIR
    DEFAULT_DOWNLOADS_DIR = str(DOWNLOADS_DIR)
    DEFAULT_VECTORDB_DIR = str(VECTORDB_DIR)
except ImportError:
    DEFAULT_DOWNLOADS_DIR = "data/downloads"
    DEFAULT_VECTORDB_DIR = "data/vectordb"

logger = logging.getLogger(__name__)

# Try to import yfinance enricher
try:
    from .yfinance_enricher import YFinanceEnricher
    ENRICHER_AVAILABLE = True
except ImportError:
    ENRICHER_AVAILABLE = False


class DataIngestionPipeline:
    """
    Pipeline for ingesting stock data from multiple sources.
    
    Workflow:
    1. Process downloaded files from each source
    2. Merge data for the same stock from different sources
    3. Calculate data quality scores
    4. Store in vector database
    
    Usage:
        pipeline = DataIngestionPipeline()
        stats = pipeline.run()
        print(f"Processed {stats['documents_added']} stocks")
    """
    
    def __init__(
        self,
        data_dir: str = None,
        vectordb_dir: str = None,
    ):
        """
        Initialize the pipeline.
        
        Args:
            data_dir: Base directory for downloaded data. Defaults to ~/.dividendscope/data/downloads.
            vectordb_dir: Directory for vector database. Defaults to ~/.dividendscope/data/vectordb.
        """
        self.data_dir = Path(data_dir or DEFAULT_DOWNLOADS_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.vector_store = VectorStore(persist_directory=vectordb_dir)
        
        self.downloaders: Dict[str, BaseDownloader] = {
            "stockquote": StockQuoteDownloader(str(self.data_dir / "stockquote")),
            "nasdaq": NasdaqDownloader(str(self.data_dir / "nasdaq")),
        }
        
        self._stats: Dict[str, int] = defaultdict(int)
    
    def run(
        self,
        sources: Optional[List[str]] = None,
        merge_strategy: str = "latest",
        enrich_with_yfinance: bool = False,
        progress_callback=None,
    ) -> Dict[str, int]:
        """
        Run the full ingestion pipeline.
        
        Args:
            sources: List of sources to process (None = all).
            merge_strategy: How to merge duplicate data:
                - "latest": Prefer most recent data
                - "complete": Prefer most complete data
                - "quality": Use data quality score
            enrich_with_yfinance: If True, enrich all documents with yfinance data.
            progress_callback: Optional callback(message, current, total) for progress.
                
        Returns:
            Statistics dict with counts of processed items.
        """
        self._stats = defaultdict(int)
        sources = sources or list(self.downloaders.keys())
        
        logger.info(f"Starting ingestion pipeline for sources: {sources}")
        
        # Step 1: Collect documents from all sources
        all_documents: Dict[str, List[StockDocument]] = defaultdict(list)
        
        for source_name in sources:
            if source_name not in self.downloaders:
                logger.warning(f"Unknown source: {source_name}")
                continue
            
            downloader = self.downloaders[source_name]
            
            logger.info(f"Processing {source_name}...")
            
            for doc in downloader.process_directory():
                all_documents[doc.symbol].append(doc)
                self._stats[f"{source_name}_parsed"] += 1
        
        logger.info(f"Collected {len(all_documents)} unique symbols")
        
        # Step 2: Merge documents for each symbol
        merged_documents: List[StockDocument] = []
        
        for symbol, docs in all_documents.items():
            merged = self._merge_documents(docs, merge_strategy)
            if merged:
                merged_documents.append(merged)
                self._stats["documents_merged"] += 1
        
        logger.info(f"Merged into {len(merged_documents)} documents")

        try:
            from config import DELISTED_SYMBOLS

            before = len(merged_documents)
            merged_documents = [
                doc for doc in merged_documents
                if doc.symbol.upper() not in DELISTED_SYMBOLS
            ]
            skipped = before - len(merged_documents)
            if skipped:
                logger.info("Skipped %s delisted symbol(s) from ingestion", skipped)
        except ImportError:
            pass
        
        # Step 3: Enrich with yfinance if requested
        if enrich_with_yfinance and ENRICHER_AVAILABLE:
            logger.info("Enriching documents with yfinance data...")
            enricher = YFinanceEnricher(request_delay=0.3)
            
            def enrich_progress(current, total):
                if progress_callback:
                    progress_callback(f"Enriching {current}/{total}", current, total)
            
            merged_documents = enricher.enrich_batch(
                merged_documents,
                progress_callback=enrich_progress,
            )
            self._stats["documents_enriched"] = len(merged_documents)
            logger.info(f"Enriched {len(merged_documents)} documents")
        
        # Step 4: Calculate data quality
        for doc in merged_documents:
            if not enrich_with_yfinance:
                doc.data_quality = self._calculate_quality(doc)
        
        # Step 5: Store in vector database
        ids = self.vector_store.add_documents(merged_documents)
        self._stats["documents_added"] = len(ids)
        
        logger.info(f"Added {len(ids)} documents to vector store")
        
        # Summary
        self._stats["total_documents"] = self.vector_store.count()
        self._stats["timestamp"] = datetime.now().isoformat()
        
        return dict(self._stats)
    
    def enrich_existing(
        self,
        symbols: Optional[List[str]] = None,
        min_quality: float = 0,
        progress_callback=None,
    ) -> Dict[str, int]:
        """
        Enrich existing documents in the vector DB with yfinance data.
        
        Args:
            symbols: Specific symbols to enrich (None = all).
            min_quality: Only enrich documents below this quality threshold.
            progress_callback: Optional callback(message, current, total) for progress.
            
        Returns:
            Statistics dict.
        """
        if not ENRICHER_AVAILABLE:
            logger.error("YFinanceEnricher not available")
            return {"error": "enricher_not_available"}
        
        stats = defaultdict(int)
        enricher = YFinanceEnricher(request_delay=0.3)
        
        # Get documents to enrich
        if symbols:
            documents = [
                self.vector_store.get_by_symbol(s) for s in symbols
            ]
            documents = [d for d in documents if d is not None]
        else:
            # Get all documents from vector store
            all_docs = []
            try:
                from config import DELISTED_SYMBOLS
            except ImportError:
                DELISTED_SYMBOLS = frozenset()
            for doc in self.vector_store.get_dividend_kings(min_streak=0):
                if doc.symbol.upper() in DELISTED_SYMBOLS:
                    continue
                if doc.data_quality < min_quality or min_quality == 0:
                    all_docs.append(doc)
            documents = all_docs
        
        total = len(documents)
        logger.info(f"Enriching {total} documents with yfinance data...")
        
        enriched = []
        for i, doc in enumerate(documents):
            try:
                enriched_doc = enricher.enrich_document(doc)
                enriched.append(enriched_doc)
                stats["enriched"] += 1
                
                if progress_callback:
                    progress_callback(
                        f"Enriching {doc.symbol}",
                        i + 1,
                        total,
                    )
            except Exception as e:
                logger.error(f"Error enriching {doc.symbol}: {e}")
                stats["errors"] += 1
        
        # Store enriched documents
        if enriched:
            self.vector_store.add_documents(enriched)
            stats["stored"] = len(enriched)
        
        stats["total_documents"] = self.vector_store.count()
        return dict(stats)
    
    def _merge_documents(
        self,
        documents: List[StockDocument],
        strategy: str,
    ) -> Optional[StockDocument]:
        """
        Merge multiple documents for the same stock.
        
        Args:
            documents: Documents to merge.
            strategy: Merge strategy.
            
        Returns:
            Merged StockDocument.
        """
        if not documents:
            return None
        
        if len(documents) == 1:
            from utils.dividend_streak import apply_dividend_streak_to_document

            apply_dividend_streak_to_document(documents[0])
            return documents[0]
        
        # Sort by preference
        if strategy == "latest":
            documents.sort(key=lambda d: d.last_updated, reverse=True)
        elif strategy == "quality":
            # Calculate quality and sort
            for doc in documents:
                doc.data_quality = self._calculate_quality(doc)
            documents.sort(key=lambda d: d.data_quality, reverse=True)
        elif strategy == "complete":
            # Sort by number of non-None fields
            documents.sort(
                key=lambda d: sum(1 for v in d.to_metadata().values() if v is not None),
                reverse=True,
            )
        
        # Use first document as base
        base = documents[0]
        
        # Merge in data from other documents
        for doc in documents[1:]:
            base = self._merge_two_documents(base, doc)
        
        # Combine data sources
        sources = list(set(d.source for d in documents))
        if len(sources) > 1:
            base.notes = f"Data from: {', '.join(s.value for s in sources)}"

        from utils.dividend_streak import apply_dividend_streak_to_document

        apply_dividend_streak_to_document(base)

        return base
    
    def _merge_two_documents(
        self,
        primary: StockDocument,
        secondary: StockDocument,
    ) -> StockDocument:
        """
        Merge secondary document into primary, filling gaps.
        
        Args:
            primary: Primary document (preferred).
            secondary: Secondary document (fallback).
            
        Returns:
            Merged document.
        """
        # Fill in missing basic info
        if primary.name == primary.symbol and secondary.name != secondary.symbol:
            primary.name = secondary.name
        
        if primary.sector == "Unknown" and secondary.sector != "Unknown":
            primary.sector = secondary.sector
        
        if primary.industry == "Unknown" and secondary.industry != "Unknown":
            primary.industry = secondary.industry
        
        if primary.exchange == "Unknown" and secondary.exchange != "Unknown":
            primary.exchange = secondary.exchange
        
        # Fill in missing dividend data
        if primary.dividend_yield is None and secondary.dividend_yield is not None:
            primary.dividend_yield = secondary.dividend_yield
        
        if primary.annual_dividend is None and secondary.annual_dividend is not None:
            primary.annual_dividend = secondary.annual_dividend
        
        if primary.dividend_streak_years is None and secondary.dividend_streak_years is not None:
            primary.dividend_streak_years = secondary.dividend_streak_years
        
        if primary.payout_ratio is None and secondary.payout_ratio is not None:
            primary.payout_ratio = secondary.payout_ratio
        
        # Fill in missing price data
        if primary.current_price is None and secondary.current_price is not None:
            primary.current_price = secondary.current_price
        
        if primary.market_cap is None and secondary.market_cap is not None:
            primary.market_cap = secondary.market_cap
        
        if primary.pe_ratio is None and secondary.pe_ratio is not None:
            primary.pe_ratio = secondary.pe_ratio
        
        # Merge historical data (combine, remove duplicates)
        if secondary.price_history:
            existing_dates = {p.date for p in primary.price_history}
            for price in secondary.price_history:
                if price.date not in existing_dates:
                    primary.price_history.append(price)
            primary.price_history.sort(key=lambda p: p.date, reverse=True)
        
        if secondary.dividend_history:
            existing_dates = {d.ex_date for d in primary.dividend_history}
            for div in secondary.dividend_history:
                if div.ex_date not in existing_dates:
                    primary.dividend_history.append(div)
            primary.dividend_history.sort(key=lambda d: d.ex_date, reverse=True)
        
        # Merge descriptions
        if secondary.description and not primary.description:
            primary.description = secondary.description
        
        return primary
    
    def _calculate_quality(self, doc: StockDocument) -> float:
        """
        Calculate data quality score (0-100).
        
        Based on:
        - Completeness of key fields
        - Amount of historical data
        - Recency of data
        """
        score = 0.0
        
        # Key dividend fields (40 points)
        if doc.dividend_yield is not None:
            score += 10
        if doc.annual_dividend is not None:
            score += 10
        if doc.dividend_streak_years is not None:
            score += 15
        if doc.payout_ratio is not None:
            score += 5
        
        # Company info (20 points)
        if doc.name and doc.name != doc.symbol:
            score += 5
        if doc.sector != "Unknown":
            score += 5
        if doc.industry != "Unknown":
            score += 5
        if doc.exchange != "Unknown":
            score += 5
        
        # Price data (15 points)
        if doc.current_price is not None:
            score += 5
        if doc.market_cap is not None:
            score += 5
        if doc.pe_ratio is not None:
            score += 5
        
        # Historical data (25 points)
        if doc.dividend_history:
            history_score = min(10, len(doc.dividend_history) / 4)  # Up to 10 pts for 40+ dividends
            score += history_score
        
        if doc.price_history:
            price_score = min(15, len(doc.price_history) / 20)  # Up to 15 pts for 300+ days
            score += price_score
        
        return min(100.0, score)
    
    def process_single_file(
        self,
        filepath: str,
        source: str = "auto",
    ) -> Tuple[int, List[str]]:
        """
        Process a single file.
        
        Args:
            filepath: Path to file.
            source: Source type ("stockquote", "nasdaq", or "auto").
            
        Returns:
            Tuple of (count, list of symbols).
        """
        path = Path(filepath)
        
        if not path.exists():
            logger.error(f"File not found: {filepath}")
            return 0, []
        
        # Auto-detect source from path or content
        if source == "auto":
            if "stockquote" in str(path).lower():
                source = "stockquote"
            elif "nasdaq" in str(path).lower():
                source = "nasdaq"
            else:
                # Default to stockquote format
                source = "stockquote"
        
        if source not in self.downloaders:
            logger.error(f"Unknown source: {source}")
            return 0, []
        
        downloader = self.downloaders[source]
        documents = downloader.parse_file(path)
        
        if not documents:
            logger.warning(f"No documents parsed from {filepath}")
            return 0, []
        
        # Calculate quality and store
        for doc in documents:
            doc.data_quality = self._calculate_quality(doc)
        
        ids = self.vector_store.add_documents(documents)
        symbols = [d.symbol for d in documents]
        
        logger.info(f"Processed {len(documents)} documents from {filepath}")
        
        return len(documents), symbols
    
    def get_stats(self) -> Dict[str, int]:
        """Get current pipeline statistics."""
        return {
            "total_documents": self.vector_store.count(),
            **dict(self._stats),
        }
    
    def search_stocks(
        self,
        query: str,
        n_results: int = 10,
        min_streak: Optional[int] = None,
        sector: Optional[str] = None,
    ):
        """
        Search for stocks in the vector database.
        
        Args:
            query: Search query.
            n_results: Max results.
            min_streak: Minimum dividend streak filter.
            sector: Sector filter.
            
        Returns:
            List of SearchResults.
        """
        where = {}
        
        if min_streak is not None:
            where["dividend_streak_years"] = {"$gte": min_streak}
        
        if sector:
            where["sector"] = sector
        
        return self.vector_store.search(
            query=query,
            n_results=n_results,
            where=where if where else None,
        )
    
    def get_dividend_kings(self) -> List[StockDocument]:
        """Get all Dividend Kings from the database."""
        return self.vector_store.get_dividend_kings(min_streak=50)
    
    def export_database(self, filepath: str) -> int:
        """Export database to JSON."""
        return self.vector_store.export_to_json(filepath)
    
    def import_database(self, filepath: str) -> int:
        """Import database from JSON."""
        return self.vector_store.import_from_json(filepath)


def create_sample_data(data_dir: str = None) -> None:
    """
    Create sample CSV files demonstrating expected formats.
    
    This helps users understand the expected file structure
    for bulk downloads from StockQuote.io and Nasdaq.
    """
    base_dir = Path(data_dir or DEFAULT_DOWNLOADS_DIR)
    
    # StockQuote sample files
    sq_dir = base_dir / "stockquote"
    sq_dir.mkdir(parents=True, exist_ok=True)
    
    # Sample fundamentals
    with open(sq_dir / "sample_fundamentals.csv", "w") as f:
        f.write("Symbol,Name,Sector,Industry,MarketCap,PE,DivYield,PayoutRatio\n")
        f.write("KO,Coca-Cola Company,Consumer Defensive,Beverages,265000000000,25.4,3.12,75.2\n")
        f.write("JNJ,Johnson & Johnson,Healthcare,Drug Manufacturers,380000000000,15.2,2.98,45.6\n")
        f.write("PG,Procter & Gamble,Consumer Defensive,Household Products,350000000000,24.1,2.45,62.3\n")
    
    # Sample dividend streaks
    with open(sq_dir / "sample_dividend_streaks.csv", "w") as f:
        f.write("Symbol,Name,ConsecutiveYears,Category\n")
        f.write("KO,Coca-Cola Company,62,King\n")
        f.write("JNJ,Johnson & Johnson,62,King\n")
        f.write("PG,Procter & Gamble,68,King\n")
        f.write("MMM,3M Company,65,King\n")
    
    # Sample dividend history
    with open(sq_dir / "sample_dividend_history.csv", "w") as f:
        f.write("Symbol,Name,Ex-Date,Payment-Date,Amount\n")
        f.write("KO,Coca-Cola Company,2024-03-14,2024-04-01,0.485\n")
        f.write("KO,Coca-Cola Company,2023-12-14,2024-01-02,0.485\n")
        f.write("KO,Coca-Cola Company,2023-09-14,2023-10-02,0.46\n")
        f.write("JNJ,Johnson & Johnson,2024-02-26,2024-03-12,1.24\n")
    
    # Nasdaq sample files
    nasdaq_dir = base_dir / "nasdaq"
    nasdaq_dir.mkdir(parents=True, exist_ok=True)
    
    # Sample historical prices
    with open(nasdaq_dir / "KO_historical.csv", "w") as f:
        f.write("Date,Close/Last,Volume,Open,High,Low\n")
        f.write("03/14/2024,$60.12,12345678,$59.85,$60.45,$59.72\n")
        f.write("03/13/2024,$59.98,11234567,$60.10,$60.25,$59.80\n")
        f.write("03/12/2024,$60.15,10345678,$59.90,$60.30,$59.75\n")
    
    # Sample dividend history
    with open(nasdaq_dir / "KO_dividends.csv", "w") as f:
        f.write("Ex/EFF DATE,TYPE,CASH AMOUNT,DECLARATION DATE,RECORD DATE,PAYMENT DATE\n")
        f.write("03/14/2024,CASH,$0.485,02/15/2024,03/15/2024,04/01/2024\n")
        f.write("12/14/2023,CASH,$0.485,10/19/2023,12/15/2023,01/02/2024\n")
    
    logger.info(f"Created sample data files in {base_dir}")
    print(f"\nSample data created in: {base_dir}")
    print("\nExpected file structure:")
    print("  data/downloads/")
    print("  ├── stockquote/")
    print("  │   ├── fundamentals.csv")
    print("  │   ├── dividend_streaks.csv")
    print("  │   └── dividend_history.csv")
    print("  └── nasdaq/")
    print("      ├── <SYMBOL>_historical.csv")
    print("      └── <SYMBOL>_dividends.csv")
