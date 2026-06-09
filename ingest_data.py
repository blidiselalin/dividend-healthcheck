#!/usr/bin/env python3
"""
Data Ingestion CLI for DividendScope.

Downloads and processes stock data from public sources into a vector database
for enhanced report generation.

Usage:
    # Run full ingestion from all sources
    python ingest_data.py
    
    # Process specific source only
    python ingest_data.py --source stockquote
    python ingest_data.py --source nasdaq
    
    # Process a single file
    python ingest_data.py --file path/to/fundamentals.csv
    
    # Create sample data files (to see expected format)
    python ingest_data.py --create-samples
    
    # Search the database
    python ingest_data.py --search "high yield dividend king"
    
    # List all dividend kings in database
    python ingest_data.py --list-kings
    
    # Export database to JSON
    python ingest_data.py --export ~/export.json
    
    # Import database from JSON
    python ingest_data.py --import ~/export.json
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.yfinance_config import configure_yfinance

configure_yfinance()

# Import config for default paths
try:
    from config import DOWNLOADS_DIR, VECTORDB_DIR
    DEFAULT_DOWNLOADS_DIR = str(DOWNLOADS_DIR)
    DEFAULT_VECTORDB_DIR = str(VECTORDB_DIR)
except ImportError:
    DEFAULT_DOWNLOADS_DIR = "data/downloads"
    DEFAULT_VECTORDB_DIR = "data/vectordb"

from data_ingestion.pipeline import DataIngestionPipeline, create_sample_data
from data_ingestion.vector_store import VectorStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

_INGESTIBLE_SUFFIXES = {".csv", ".json"}


def _downloads_have_ingestible_files(data_path: Path) -> bool:
    """True if stockquote/nasdaq (or data root) contains files the pipeline can parse."""
    if not data_path.exists():
        return False
    for path in data_path.rglob("*"):
        if path.is_file() and path.suffix.lower() in _INGESTIBLE_SUFFIXES:
            return True
    return False


def _run_enrich_without_downloads(pipeline: DataIngestionPipeline) -> int:
    """Docker/cloud path: populate shared S&P library and enrich (no CSV downloads)."""
    from services.portfolio_vector_sync import sync_portfolio_to_vector_db
    from services.sp500_peers_service import coverage_stats, ensure_sp500_in_vectordb

    print("No CSV/JSON files in downloads — shared market DB + yfinance enrich.\n")

    print("Step 1: Ensure S&P 500 symbols in shared analysed-stocks DB")

    def sp500_progress(msg, current, total):
        pct = (current / total) * 100 if total > 0 else 0
        print(f"\r[{pct:5.1f}%] {msg}...", end="", flush=True)

    sp500_stats = ensure_sp500_in_vectordb(progress_callback=sp500_progress)
    print("\n")
    after = coverage_stats()
    print(
        f"  S&P coverage: {after['analysed_sp500']}/{after['universe_total']} "
        f"({after['pct_covered']:.0f}%) · new docs: {sp500_stats.get('created', 0)}"
    )
    print()

    print("Step 2: Enrich all documents in shared vector DB (yfinance)")

    def progress_cb(msg, current, total):
        pct = (current / total) * 100 if total > 0 else 0
        print(f"\r[{pct:5.1f}%] {msg}...", end="", flush=True)

    stats = pipeline.enrich_existing(progress_callback=progress_cb)
    print("\n")
    print("Enrichment complete!")
    print(f"  Documents enriched: {stats.get('enriched', 0)}")
    print(f"  Errors: {stats.get('errors', 0)}")
    print(f"  Total documents: {stats.get('total_documents', 0)}")
    print()

    print("Step 3: Link current portfolio holdings → vector DB (optional)")
    sync_stats = sync_portfolio_to_vector_db(enrich_missing=True)
    print(f"  Holdings linked: {sync_stats.get('linked', 0)}")
    print(f"  New documents:   {sync_stats.get('created', 0)}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Ingest stock data from public sources into vector database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ingest_data.py                    # Full ingestion from all sources
  python ingest_data.py --source nasdaq    # Process Nasdaq files only
  python ingest_data.py --create-samples   # Create sample CSV files
  python ingest_data.py --search "tech dividend"  # Search database
        """,
    )
    
    # Action arguments
    parser.add_argument(
        "--source",
        choices=["stockquote", "nasdaq", "all"],
        default="all",
        help="Data source to process (default: all)",
    )
    
    parser.add_argument(
        "--file",
        type=str,
        help="Process a single file",
    )
    
    parser.add_argument(
        "--create-samples",
        action="store_true",
        help="Create sample data files showing expected format",
    )
    
    parser.add_argument(
        "--search",
        type=str,
        help="Search the vector database",
    )
    
    parser.add_argument(
        "--list-kings",
        action="store_true",
        help="List all Dividend Kings in database",
    )
    
    parser.add_argument(
        "--export",
        type=str,
        help="Export database to JSON file",
    )
    
    parser.add_argument(
        "--import",
        dest="import_file",
        type=str,
        help="Import database from JSON file",
    )
    
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show database statistics",
    )
    
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear the vector database",
    )
    
    parser.add_argument(
        "--consolidate",
        action="store_true",
        help="Consolidate duplicates and trim history to 10 years",
    )
    
    parser.add_argument(
        "--fix-values",
        action="store_true",
        help="Fix invalid/corrupt values (yields > 30%%, payout > 150%%)",
    )

    parser.add_argument(
        "--refresh-prices",
        action="store_true",
        help="Update current_price in the vector DB from live market quotes",
    )

    parser.add_argument(
        "--hourly-update",
        action="store_true",
        help="Scheduled refresh: live prices, S&P catch-up, enrich stale documents",
    )

    parser.add_argument(
        "--hourly-enrich-limit",
        type=int,
        default=40,
        help="With --hourly-update, max stale symbols to enrich per run (default: 40)",
    )

    parser.add_argument(
        "--hourly-stale-days",
        type=int,
        default=7,
        help="With --hourly-update, re-enrich if last_updated older than N days (default: 7)",
    )

    parser.add_argument(
        "--remove-delisted",
        action="store_true",
        help="Remove delisted symbols (WBA, SJW, LANC, BF.B) from the vector DB",
    )
    
    # Configuration
    parser.add_argument(
        "--data-dir",
        type=str,
        default=DEFAULT_DOWNLOADS_DIR,
        help=f"Directory containing downloaded data (default: {DEFAULT_DOWNLOADS_DIR})",
    )
    
    parser.add_argument(
        "--db-dir",
        type=str,
        default=DEFAULT_VECTORDB_DIR,
        help=f"Directory for vector database (default: {DEFAULT_VECTORDB_DIR})",
    )
    
    parser.add_argument(
        "--merge-strategy",
        choices=["latest", "complete", "quality"],
        default="quality",
        help="Strategy for merging duplicate data (default: quality)",
    )
    
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Enrich documents with yfinance data (adds valuation, financials, etc.)",
    )
    
    parser.add_argument(
        "--enrich-existing",
        action="store_true",
        help="Enrich existing documents in the database with yfinance data",
    )

    parser.add_argument(
        "--backfill-history",
        action="store_true",
        help=(
            "Backfill price_history and dividend_history for library rows missing "
            "yield-channel data (252+ prices, 4+ dividends)"
        ),
    )
    parser.add_argument(
        "--backfill-limit",
        type=int,
        default=40,
        help="With --backfill-history, max symbols per run (default: 40)",
    )

    parser.add_argument(
        "--sync-history-tables",
        action="store_true",
        help=(
            "Copy price_history and dividend_history from stock_documents JSONB "
            "into stock_price_history / stock_dividend_history tables"
        ),
    )
    parser.add_argument(
        "--sync-history-limit",
        type=int,
        default=500,
        help="With --sync-history-tables, max pending symbols per run (default: 500)",
    )
    parser.add_argument(
        "--sync-history-all",
        action="store_true",
        help="With --sync-history-tables, scan first N symbols alphabetically (ignore pending filter)",
    )

    parser.add_argument(
        "--sync-portfolio",
        action="store_true",
        help="Link portfolio.db holdings into the vector DB (creates missing symbols via yfinance)",
    )

    parser.add_argument(
        "--ensure-sp500",
        action="store_true",
        help="Add missing S&P 500 constituents to analysed stocks (yfinance enrich)",
    )

    parser.add_argument(
        "--sp500-limit",
        type=int,
        default=None,
        help="With --ensure-sp500, max new tickers to fetch this run",
    )
    
    parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated list of symbols to enrich (for --enrich-existing)",
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Handle actions
    if args.create_samples:
        create_sample_data(args.data_dir)
        return 0
    
    # Initialize pipeline
    pipeline = DataIngestionPipeline(
        data_dir=args.data_dir,
        vectordb_dir=args.db_dir,
    )
    
    if args.clear:
        confirm = input("Clear all data from vector database? [y/N]: ")
        if confirm.lower() == "y":
            pipeline.vector_store.clear()
            print("Database cleared.")
        return 0
    
    if args.consolidate:
        print(f"\n{'='*50}")
        print("  CONSOLIDATING DATABASE")
        print(f"{'='*50}\n")
        
        print("This will:")
        print("  - Remove duplicate documents (keep best data)")
        print("  - Trim historical data to 10 years")
        print("  - Merge enriched data from all sources")
        print()
        
        stats = pipeline.vector_store.consolidate_duplicates()
        
        print("\n✓ Consolidation complete!")
        print(f"  Documents before: {stats['total_before']}")
        print(f"  Unique symbols: {stats['unique_symbols']}")
        print(f"  Duplicates removed: {stats['duplicates_removed']}")
        print(f"  Documents after: {stats['total_after']}")
        return 0
    
    if args.fix_values:
        print(f"\n{'='*50}")
        print("  FIXING INVALID VALUES")
        print(f"{'='*50}\n")
        
        stats = pipeline.vector_store.fix_invalid_values()
        
        print("\n✓ Value fixes complete!")
        print(f"  Total documents: {stats['total_documents']}")
        print(f"  Yield fixes: {stats['yield_fixes']}")
        print(f"  Payout ratio fixes: {stats['payout_fixes']}")
        return 0

    if args.hourly_update:
        from services.hourly_market_update import run_hourly_market_update

        print(f"\n{'='*50}")
        print("  HOURLY MARKET UPDATE")
        print(f"{'='*50}\n")

        summary = run_hourly_market_update(
            stale_days=args.hourly_stale_days,
            enrich_limit=args.hourly_enrich_limit,
        )
        prices = summary.get("prices") or {}
        sp500 = summary.get("sp500") or {}
        enrich = summary.get("enrich") or {}

        print("✓ Hourly update complete!")
        print(f"  Prices updated:  {prices.get('updated', 0)} / {prices.get('total', 0)}")
        print(f"  S&P new docs:    {sp500.get('created', 0)}")
        print(
            f"  Stale enriched:  {enrich.get('enriched', 0)} "
            f"(candidates {enrich.get('candidates', 0)})"
        )
        print(f"  Elapsed:         {summary.get('elapsed_seconds', 0)}s")
        return 0

    if args.refresh_prices:
        from services.db_price_refresh import refresh_vector_db_prices

        print(f"\n{'='*50}")
        print("  REFRESHING LATEST PRICES IN VECTOR DB")
        print(f"{'='*50}\n")

        stats = refresh_vector_db_prices()
        print("\n✓ Price refresh complete!")
        print(f"  Symbols targeted: {stats['total']}")
        print(f"  Updated: {stats['updated']}")
        print(f"  Skipped: {stats['skipped']}")
        print(f"  Errors: {stats['errors']}")
        return 0

    if args.remove_delisted:
        from services.db_price_refresh import remove_delisted_from_vector_db

        print(f"\n{'='*50}")
        print("  REMOVING DELISTED SYMBOLS FROM VECTOR DB")
        print(f"{'='*50}\n")

        stats = remove_delisted_from_vector_db()
        print("\n✓ Delisted symbols removed!")
        print(f"  Symbols: {', '.join(stats['symbols'])}")
        print(f"  Documents removed: {stats['removed']}")
        return 0
    
    if args.stats:
        stats = pipeline.get_stats()
        print("\n=== Vector Database Statistics ===")
        print(f"Total documents: {stats.get('total_documents', 0)}")
        
        # Count by source
        kings = pipeline.get_dividend_kings()
        print(f"Dividend Kings (50+ years): {len(kings)}")
        
        return 0
    
    if args.search:
        results = pipeline.search_stocks(args.search, n_results=10)
        
        print(f"\n=== Search Results for '{args.search}' ===\n")
        
        if not results:
            print("No results found.")
            return 0
        
        for i, result in enumerate(results, 1):
            doc = result.document
            streak = f"{doc.dividend_streak_years}yr" if doc.dividend_streak_years else "N/A"
            yld = f"{doc.dividend_yield:.2f}%" if doc.dividend_yield else "N/A"
            print(f"{i}. {doc.symbol} - {doc.name}")
            print(f"   Sector: {doc.sector} | Streak: {streak} | Yield: {yld}")
            print(f"   Score: {result.score:.3f}")
            print()
        
        return 0
    
    if args.list_kings:
        kings = pipeline.get_dividend_kings()
        
        print(f"\n=== Dividend Kings in Database ({len(kings)}) ===\n")
        
        if not kings:
            print("No Dividend Kings found. Run ingestion first.")
            return 0
        
        # Sort by streak
        kings.sort(key=lambda d: d.dividend_streak_years or 0, reverse=True)
        
        for doc in kings:
            streak = doc.dividend_streak_years or 0
            yld = f"{doc.dividend_yield:.2f}%" if doc.dividend_yield else "N/A"
            print(f"👑 {doc.symbol:6} {doc.name[:30]:30} | {streak:2}yr | {yld}")
        
        return 0
    
    if args.export:
        count = pipeline.export_database(args.export)
        print(f"Exported {count} documents to {args.export}")
        return 0
    
    if args.import_file:
        count = pipeline.import_database(args.import_file)
        print(f"Imported {count} documents from {args.import_file}")
        return 0
    
    if args.file:
        count, symbols = pipeline.process_single_file(args.file)
        print(f"\nProcessed {count} stocks: {', '.join(symbols)}")
        return 0
    
    if args.sync_portfolio:
        from services.portfolio_vector_sync import sync_portfolio_to_vector_db

        print(f"\n{'='*50}")
        print("  SYNC PORTFOLIO → ANALYSED STOCKS")
        print(f"{'='*50}\n")
        stats = sync_portfolio_to_vector_db(enrich_missing=True)
        print(f"  Holdings linked: {stats.get('linked', 0)}")
        print(f"  New documents:   {stats.get('created', 0)}")
        print(f"  Stored:          {stats.get('stored', 0)}")
        print(f"  Errors:          {stats.get('errors', 0)}")
        if stats.get("still_missing"):
            print(f"  Still missing:   {', '.join(stats['still_missing'])}")
        print(f"  Total in DB:     {stats.get('total_documents', 0)}")
        return 0

    if args.ensure_sp500:
        from services.sp500_peers_service import coverage_stats, ensure_sp500_in_vectordb

        print(f"\n{'='*50}")
        print("  S&P 500 → ANALYSED STOCKS")
        print(f"{'='*50}\n")
        before = coverage_stats()
        print(
            f"  Coverage before: {before['analysed_sp500']}/{before['universe_total']} "
            f"({before['pct_covered']:.0f}%)"
        )

        def progress_cb(msg, current, total):
            pct = (current / total) * 100 if total > 0 else 0
            print(f"\r[{pct:5.1f}%] {msg}...", end="", flush=True)

        stats = ensure_sp500_in_vectordb(
            limit=args.sp500_limit,
            progress_callback=progress_cb,
        )
        print("\n")
        after = coverage_stats()
        print("✓ S&P 500 ingest complete!")
        print(f"  New documents:   {stats.get('created', 0)}")
        print(f"  Errors:          {stats.get('errors', 0)}")
        print(
            f"  Coverage after:  {after['analysed_sp500']}/{after['universe_total']} "
            f"({after['pct_covered']:.0f}%)"
        )
        print(f"  Total analysed:  {after['analysed_total']}")
        return 0

    if args.sync_history_tables:
        print(f"\n{'='*50}")
        print("  SYNC JSONB HISTORY → NORMALIZED TABLES")
        print(f"{'='*50}\n")
        from db.postgres_market_history_store import PostgresMarketHistoryStore

        symbols = args.symbols.split(",") if args.symbols else None
        stats = PostgresMarketHistoryStore().backfill_from_document_jsonb(
            symbols=symbols,
            limit=max(1, args.sync_history_limit),
            pending_only=not getattr(args, "sync_history_all", False),
        )
        print("History table sync complete!")
        print(f"  Pending:   {stats.get('pending', stats.get('processed', 0))}")
        print(f"  Processed: {stats.get('processed', 0)}")
        print(f"  Synced:    {stats.get('synced', 0)}")
        print(f"  Skipped:   {stats.get('skipped', 0)}")
        if stats.get("synced", 0) > 0 and not symbols and stats.get("pending", 0) >= args.sync_history_limit:
            print("  Tip: re-run until Pending/Synced drop (or use --sync-history-all)")
        return 0

    # Handle backfill-history action
    if args.backfill_history:
        print(f"\n{'='*50}")
        print("  BACKFILLING THIN PRICE/DIVIDEND HISTORY")
        print(f"{'='*50}\n")

        symbols = args.symbols.split(",") if args.symbols else None
        from services.stock_history_backfill import backfill_thin_history, thin_history_summary

        before = thin_history_summary()
        print(
            f"  Library: {before['yield_ready']}/{before['total']} yield-ready "
            f"({before['thin_history']} thin)"
        )

        def progress_cb(value, message):
            pct = value * 100
            print(f"\r[{pct:5.1f}%] {message}...", end="", flush=True)

        stats = backfill_thin_history(
            limit=max(1, args.backfill_limit),
            symbols=symbols,
            progress_callback=progress_cb,
        )
        after = thin_history_summary()
        print("\n")
        print("History backfill complete!")
        print(f"  Candidates:     {stats.get('candidates', 0)}")
        print(f"  Processed:        {stats.get('processed', 0)}")
        print(f"  Enriched:         {stats.get('enriched', 0)}")
        print(f"  Yield-ready now:  {stats.get('ready_after', 0)} this batch")
        print(
            f"  Library total:    {after['yield_ready']}/{after['total']} yield-ready "
            f"({after['thin_history']} thin remaining)"
        )
        return 0

    # Handle enrich-existing action
    if args.enrich_existing:
        print(f"\n{'='*50}")
        print("  ENRICHING EXISTING DOCUMENTS")
        print(f"{'='*50}\n")
        
        symbols = args.symbols.split(",") if args.symbols else None
        
        def progress_cb(msg, current, total):
            pct = (current / total) * 100 if total > 0 else 0
            print(f"\r[{pct:5.1f}%] {msg}...", end="", flush=True)
        
        stats = pipeline.enrich_existing(
            symbols=symbols,
            progress_callback=progress_cb,
        )
        
        print("\n")
        print("Enrichment complete!")
        print(f"  Documents enriched: {stats.get('enriched', 0)}")
        print(f"  Errors: {stats.get('errors', 0)}")
        print(f"  Total documents: {stats.get('total_documents', 0)}")
        return 0
    
    # Run full pipeline
    sources = None if args.source == "all" else [args.source]
    
    print(f"\n{'='*50}")
    print("  DIVIDEND KINGS DATA INGESTION PIPELINE")
    print(f"{'='*50}\n")
    
    print(f"Data directory: {args.data_dir}")
    print(f"Database directory: {args.db_dir}")
    print(f"Sources: {args.source}")
    print(f"Merge strategy: {args.merge_strategy}")
    print(f"Enrich with yfinance: {args.enrich}")
    print()
    
    data_path = Path(args.data_dir)
    has_download_files = _downloads_have_ingestible_files(data_path)

    if args.enrich and not has_download_files:
        print(f"\n{'='*50}")
        print("  DIVIDEND KINGS DATA INGESTION (yfinance)")
        print(f"{'='*50}\n")
        print(f"Database directory: {args.db_dir}")
        return _run_enrich_without_downloads(pipeline)

    if not has_download_files:
        print("⚠️  No CSV/JSON data files found!")
        print()
        print("Docker / cloud (portfolio only):")
        print("  python ingest_data.py --enrich")
        print("  python ingest_data.py --sync-portfolio")
        print("  python ingest_data.py --enrich-existing")
        print()
        print("Full file-based ingestion:")
        print("  1. Create sample files:  python ingest_data.py --create-samples")
        print("  2. Download real data from StockQuote.io and Nasdaq")
        print("  3. Place files in:")
        print(f"     - StockQuote: {data_path}/stockquote/")
        print(f"     - Nasdaq: {data_path}/nasdaq/")
        print()
        return 1
    
    def progress_cb(msg, current, total):
        if args.enrich:
            pct = (current / total) * 100 if total > 0 else 0
            print(f"\r[{pct:5.1f}%] {msg}...", end="", flush=True)
    
    # Run ingestion
    stats = pipeline.run(
        sources=sources,
        merge_strategy=args.merge_strategy,
        enrich_with_yfinance=args.enrich,
        progress_callback=progress_cb if args.enrich else None,
    )
    
    if args.enrich:
        print()  # New line after progress
    
    # Print results
    print("\n" + "="*50)
    print("  INGESTION COMPLETE")
    print("="*50 + "\n")
    
    print("Statistics:")
    for key, value in sorted(stats.items()):
        if key != "timestamp":
            print(f"  {key}: {value}")
    
    print()
    print(f"✓ Vector database ready at: {args.db_dir}")
    print()
    
    # Show kings
    kings = pipeline.get_dividend_kings()
    if kings:
        print(f"Dividend Kings found: {len(kings)}")
        for doc in kings[:5]:
            print(f"  👑 {doc.symbol} - {doc.dividend_streak_years} years")
        if len(kings) > 5:
            print(f"  ... and {len(kings) - 5} more")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
