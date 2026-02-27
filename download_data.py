#!/usr/bin/env python3
"""
Unified Data Download Script for DividendScope.

Downloads stock exchange data from multiple public sources:
- StockQuote.io: Dividend Kings/Aristocrats lists, fundamentals, dividend history
- Nasdaq: Historical prices and dividend payment history

Usage:
    # Download all data (dividend kings + aristocrats + history)
    python download_data.py
    
    # Download only from specific source
    python download_data.py --source stockquote
    python download_data.py --source nasdaq --symbols KO JNJ PG
    
    # Download specific symbols
    python download_data.py --symbols KO JNJ PG MMM
    
    # Skip certain data types
    python download_data.py --no-prices
    python download_data.py --no-history
    
    # Then run ingestion to populate vector database
    python ingest_data.py
"""

import argparse
import logging
import sys

# Import config for default paths
try:
    from config import DOWNLOADS_DIR, VECTORDB_DIR
    DEFAULT_DOWNLOADS_DIR = str(DOWNLOADS_DIR)
    DEFAULT_VECTORDB_DIR = str(VECTORDB_DIR)
except ImportError:
    DEFAULT_DOWNLOADS_DIR = "data/downloads"
    DEFAULT_VECTORDB_DIR = "data/vectordb"
from pathlib import Path
from typing import List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Import stock lists from central config
from config import DIVIDEND_KINGS, DIVIDEND_ARISTOCRATS

logger = logging.getLogger(__name__)


def download_stockquote(
    output_dir: str,
    symbols: Optional[List[str]] = None,
    include_history: bool = True,
    verbose: bool = False,
) -> bool:
    """Download data from StockQuote.io."""
    try:
        from data_ingestion.fetch_stockquote import StockQuoteFetcher
        
        logger.info("=" * 50)
        logger.info("Downloading from StockQuote.io...")
        logger.info("=" * 50)
        
        fetcher = StockQuoteFetcher(output_dir=output_dir)
        stats = fetcher.download_all(
            symbols=symbols,
            include_history=include_history,
        )
        
        print(f"\n✓ StockQuote.io download complete:")
        print(f"  - Dividend Kings: {stats.get('kings', 0)}")
        print(f"  - Dividend Aristocrats: {stats.get('aristocrats', 0)}")
        print(f"  - Stock details: {stats.get('details', 0)}")
        print(f"  - Dividend records: {stats.get('dividends', 0)}")
        
        return True
        
    except ImportError as e:
        logger.error(f"Missing dependencies for StockQuote.io: {e}")
        print("\n⚠ StockQuote.io requires: pip install requests beautifulsoup4")
        return False
    except Exception as e:
        logger.error(f"StockQuote.io download failed: {e}")
        return False


def download_nasdaq(
    output_dir: str,
    symbols: List[str],
    include_prices: bool = True,
    include_dividends: bool = True,
    include_info: bool = True,
    verbose: bool = False,
) -> bool:
    """Download data from Nasdaq.com."""
    try:
        from data_ingestion.fetch_nasdaq import NasdaqFetcher
        
        logger.info("=" * 50)
        logger.info(f"Downloading from Nasdaq.com ({len(symbols)} symbols)...")
        logger.info("=" * 50)
        
        fetcher = NasdaqFetcher(output_dir=output_dir)
        stats = fetcher.download_multiple(
            symbols=symbols,
            include_prices=include_prices,
            include_dividends=include_dividends,
            include_info=include_info,
        )
        
        print(f"\n✓ Nasdaq download complete:")
        print(f"  - Symbols processed: {stats.get('symbols_processed', 0)}")
        print(f"  - Price records: {stats.get('prices_downloaded', 0)}")
        print(f"  - Dividend records: {stats.get('dividends_downloaded', 0)}")
        print(f"  - Company info: {stats.get('info_downloaded', 0)}")
        if stats.get('errors', 0):
            print(f"  - Errors: {stats['errors']}")
        
        return True
        
    except ImportError as e:
        logger.error(f"Missing dependencies for Nasdaq: {e}")
        print("\n⚠ Nasdaq requires: pip install requests")
        return False
    except Exception as e:
        logger.error(f"Nasdaq download failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Download stock data from public sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python download_data.py                     # Download all data
  python download_data.py --source nasdaq     # Nasdaq only
  python download_data.py --symbols KO JNJ    # Specific symbols
  python download_data.py --kings-only        # Only Dividend Kings
        """,
    )
    
    # Source selection
    parser.add_argument(
        "--source",
        choices=["all", "stockquote", "nasdaq"],
        default="all",
        help="Data source to download from (default: all)",
    )
    
    # Symbol selection
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Specific symbols to download (default: all dividend kings + aristocrats)",
    )
    parser.add_argument(
        "--kings-only",
        action="store_true",
        help="Download only Dividend Kings (skip Aristocrats)",
    )
    parser.add_argument(
        "--symbols-file",
        type=str,
        help="File with symbols (one per line)",
    )
    
    # Data type selection
    parser.add_argument(
        "--no-prices",
        action="store_true",
        help="Skip downloading historical prices",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Skip downloading dividend history",
    )
    parser.add_argument(
        "--no-info",
        action="store_true",
        help="Skip downloading company info",
    )
    
    # Output configuration
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_DOWNLOADS_DIR,
        help=f"Base output directory (default: {DEFAULT_DOWNLOADS_DIR})",
    )
    
    # Other options
    parser.add_argument(
        "--run-ingestion",
        action="store_true",
        help="Run ingestion pipeline after download",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    print("\n" + "=" * 60)
    print("  DIVIDEND KINGS DATA DOWNLOADER")
    print("=" * 60)
    
    # Determine symbols to download
    if args.symbols:
        symbols = [s.upper().strip() for s in args.symbols]
    elif args.symbols_file:
        try:
            with open(args.symbols_file, "r") as f:
                symbols = [line.strip().upper() for line in f if line.strip()]
        except FileNotFoundError:
            print(f"Error: Symbols file not found: {args.symbols_file}")
            return 1
    elif args.kings_only:
        symbols = list(DIVIDEND_KINGS)
    else:
        # All dividend stocks
        symbols = list(set(DIVIDEND_KINGS + DIVIDEND_ARISTOCRATS))
    
    print(f"\nSymbols to download: {len(symbols)}")
    print(f"Output directory: {args.output_dir}")
    print(f"Sources: {args.source}")
    print()
    
    # Create output directories
    base_dir = Path(args.output_dir)
    stockquote_dir = base_dir / "stockquote"
    nasdaq_dir = base_dir / "nasdaq"
    
    stockquote_dir.mkdir(parents=True, exist_ok=True)
    nasdaq_dir.mkdir(parents=True, exist_ok=True)
    
    success = True
    
    # Download from StockQuote.io
    if args.source in ["all", "stockquote"]:
        result = download_stockquote(
            output_dir=str(stockquote_dir),
            symbols=symbols if args.symbols else None,  # None = discover from site
            include_history=not args.no_history,
            verbose=args.verbose,
        )
        success = success and result
    
    # Download from Nasdaq
    if args.source in ["all", "nasdaq"]:
        result = download_nasdaq(
            output_dir=str(nasdaq_dir),
            symbols=symbols,
            include_prices=not args.no_prices,
            include_dividends=not args.no_history,
            include_info=not args.no_info,
            verbose=args.verbose,
        )
        success = success and result
    
    print("\n" + "=" * 60)
    
    if success:
        print("✓ Download completed successfully!")
        print(f"\nFiles saved to:")
        print(f"  - StockQuote.io: {stockquote_dir}")
        print(f"  - Nasdaq: {nasdaq_dir}")
        
        # Run ingestion if requested
        if args.run_ingestion:
            print("\n" + "=" * 60)
            print("Running data ingestion...")
            print("=" * 60)
            
            try:
                from data_ingestion.pipeline import DataIngestionPipeline
                
                pipeline = DataIngestionPipeline(
                    data_dir=args.output_dir,
                    vectordb_dir=DEFAULT_VECTORDB_DIR,
                )
                stats = pipeline.run()
                
                print(f"\n✓ Ingestion complete!")
                print(f"  - Documents added: {stats.get('documents_added', 0)}")
                print(f"  - Total in database: {stats.get('total_documents', 0)}")
                
            except Exception as e:
                print(f"\n⚠ Ingestion failed: {e}")
        else:
            print("\nNext step: Run ingestion to populate vector database:")
            print("  python ingest_data.py")
    else:
        print("⚠ Some downloads failed. Check errors above.")
        return 1
    
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
