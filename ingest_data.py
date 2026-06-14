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
from tempfile import NamedTemporaryFile

import requests

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Import config for default paths
try:
    from config import DOWNLOADS_DIR, VECTORDB_DIR

    DEFAULT_DOWNLOADS_DIR = str(DOWNLOADS_DIR)
    DEFAULT_VECTORDB_DIR = str(VECTORDB_DIR)
except ImportError:
    DEFAULT_DOWNLOADS_DIR = "data/downloads"
    DEFAULT_VECTORDB_DIR = "data/vectordb"

from data_ingestion.pipeline import DataIngestionPipeline, create_sample_data
from services.snapshot_sync_service import google_drive_direct_download_url

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _downloads_have_ingestible_files(data_dir: str) -> bool:
    """Check if the downloads directory has files to process."""
    path = Path(data_dir)
    if not path.exists():
        return False
    return any(path.rglob("*.csv")) or any(path.rglob("*.json"))


def main() -> int:  # noqa: C901
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
        "--import-url",
        type=str,
        help="Import database snapshot from URL (supports Google Drive links)",
    )

    parser.add_argument(
        "--export-snapshot",
        type=str,
        help="Export database snapshot JSON (for manual upload to Drive)",
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
        help="Fix invalid/corrupt values (yields over 30 percent, payout over 500 percent)",
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
        "--symbols",
        type=str,
        help="Comma-separated list of symbols to enrich (for --enrich-existing)",
    )

    parser.add_argument(
        "--add-symbols",
        type=str,
        dest="add_symbols",
        help="Comma-separated symbols to add directly from yfinance (e.g. INTU,MSFT)",
    )

    parser.add_argument(
        "--sync-history-tables",
        action="store_true",
        help="Sync JSONB history into stock_price_history and stock_dividend_history tables",
    )

    parser.add_argument(
        "--sync-history-limit",
        type=int,
        default=500,
        help="Max symbols to sync for --sync-history-tables (default: 500)",
    )

    parser.add_argument(
        "--ensure-sp500",
        action="store_true",
        help="Fetch and populate missing S&P 500 constituents",
    )

    parser.add_argument(
        "--backfill-history",
        action="store_true",
        help="Backfill thin price/dividend history from yfinance",
    )

    parser.add_argument(
        "--backfill-limit",
        type=int,
        default=40,
        help="Max symbols to backfill for --backfill-history (default: 40)",
    )

    parser.add_argument(
        "--refresh-prices",
        action="store_true",
        help="Refresh latest prices for existing market library documents",
    )

    parser.add_argument(
        "--ensure-top-dividend",
        action="store_true",
        help="Fetch and populate missing top 100 dividend payers",
    )

    parser.add_argument(
        "--limit",
        type=int,
        help="Max symbols for --ensure-sp500 or --ensure-top-dividend",
    )

    parser.add_argument(
        "--sync-portfolio",
        action="store_true",
        help="Sync portfolio holdings into stock_documents",
    )

    parser.add_argument(
        "--hourly-update",
        action="store_true",
        help=(
            "Hourly market refresh: refresh all prices, add up to 5 missing S&P tickers, "
            "enrich up to 40 stale documents (quality < 55%% or older than 7 days)"
        ),
    )

    parser.add_argument(
        "-v",
        "--verbose",
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

    if args.sync_history_tables:
        from db.postgres_market_history_store import PostgresMarketHistoryStore

        stats = PostgresMarketHistoryStore().sync_pending_from_jsonb(limit=args.sync_history_limit)
        print("History table sync complete!")
        print(f"  Pending: {stats.get('pending', 0)}")
        print(f"  Processed: {stats.get('processed', 0)}")
        print(f"  Synced: {stats.get('synced', 0)}")
        print(f"  Skipped: {stats.get('skipped', 0)}")
        return 0

    if args.ensure_sp500:
        from services.sp500_peers_service import ensure_sp500_in_vectordb

        def progress_cb_sp500(msg: str, current: int, total: int) -> None:
            pct = (current / total) * 100 if total > 0 else 0
            print(f"\r[{pct:5.1f}%] {msg}...", end="", flush=True)

        stats = ensure_sp500_in_vectordb(limit=args.limit, progress_callback=progress_cb_sp500)
        if stats.get("created", 0) or stats.get("errors", 0):
            print()
        print("S&P 500 ingest complete!")
        print(f"  Created: {stats.get('created', 0)}")
        print(f"  Already present: {stats.get('already_present', 0)}")
        print(f"  Errors: {stats.get('errors', 0)}")
        return 0

    if args.backfill_history:
        from services.stock_history_backfill import backfill_thin_history

        def progress_cb_backfill(pct: float, msg: str) -> None:
            print(f"\r[{pct * 100:5.1f}%] {msg}...", end="", flush=True)

        stats = backfill_thin_history(
            limit=args.backfill_limit,
            progress_callback=progress_cb_backfill,
        )
        if stats.get("processed", 0):
            print()
        print("History backfill complete!")
        print(f"  Candidates: {stats.get('candidates', 0)}")
        print(f"  Processed: {stats.get('processed', 0)}")
        print(f"  Enriched: {stats.get('enriched', 0)}")
        print(f"  Ready after: {stats.get('ready_after', 0)}")
        print(f"  Errors: {stats.get('errors', 0)}")
        return 0

    if args.refresh_prices:
        from services.db_price_refresh import refresh_market_library_prices

        stats = refresh_market_library_prices()
        print("Price refresh complete!")
        print(f"  Total: {stats.get('total', 0)}")
        print(f"  Updated: {stats.get('updated', 0)}")
        print(f"  Skipped: {stats.get('skipped', 0)}")
        print(f"  Errors: {stats.get('errors', 0)}")
        return 0

    if args.hourly_update:
        # Composite hourly refresh: prices → S&P catch-up (5) → stale enrich (40, quality < 55%)
        print("=== Hourly market refresh ===")

        from services.db_price_refresh import refresh_market_library_prices

        price_stats = refresh_market_library_prices()
        print(
            f"  Prices refreshed: {price_stats.get('updated', 0)}"
            f" / {price_stats.get('total', 0)}"
            f" (errors: {price_stats.get('errors', 0)})"
        )

        from services.sp500_peers_service import ensure_sp500_in_vectordb

        sp500_stats = ensure_sp500_in_vectordb(limit=5)
        print(
            f"  S&P catch-up: created {sp500_stats.get('created', 0)}"
            f" (errors: {sp500_stats.get('errors', 0)})"
        )

        pipeline = DataIngestionPipeline(
            data_dir=args.data_dir,
            vectordb_dir=args.db_dir,
        )
        enrich_stats = pipeline.enrich_existing(min_quality=0.55)
        print(
            f"  Enriched: {enrich_stats.get('enriched', 0)}"
            f" (errors: {enrich_stats.get('errors', 0)})"
        )

        print("=== Hourly refresh done ===")
        return 0

    if args.ensure_top_dividend:
        from services.sp500_peers_service import ensure_top_dividend_in_vectordb

        def progress_cb_top_dividend(msg: str, current: int, total: int) -> None:
            pct = (current / total) * 100 if total > 0 else 0
            print(f"\r[{pct:5.1f}%] {msg}...", end="", flush=True)

        stats = ensure_top_dividend_in_vectordb(
            limit=args.limit,
            progress_callback=progress_cb_top_dividend,
        )
        if stats.get("created", 0) or stats.get("errors", 0):
            print()
        print("Top dividend ingest complete!")
        print(f"  Created: {stats.get('created', 0)}")
        print(f"  Already present: {stats.get('already_present', 0)}")
        print(f"  Errors: {stats.get('errors', 0)}")
        return 0

    if args.sync_portfolio:
        from services.portfolio_vector_sync import sync_portfolio_to_vector_db

        stats = sync_portfolio_to_vector_db()
        print("Portfolio sync complete!")
        print(f"  Linked: {stats.get('linked', 0)}")
        print(f"  Created: {stats.get('created', 0)}")
        print(f"  Stored: {stats.get('stored', 0)}")
        print(f"  Missing: {len(stats.get('still_missing', []))}")
        print(f"  Errors: {stats.get('errors', 0)}")
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
        print(f"\n{'=' * 50}")
        print("  CONSOLIDATING DATABASE")
        print(f"{'=' * 50}\n")

        print("This will:")
        print("  - Remove duplicate documents (keep best data)")
        print("  - Trim historical data to 10 years")
        print("  - Merge enriched data from all sources")
        print()

        consolidate_stats = pipeline.vector_store.consolidate_duplicates()

        print("\n✓ Consolidation complete!")
        print(f"  Documents before: {consolidate_stats['total_before']}")
        print(f"  Unique symbols: {consolidate_stats['unique_symbols']}")
        print(f"  Duplicates removed: {consolidate_stats['duplicates_removed']}")
        print(f"  Documents after: {consolidate_stats['total_after']}")
        return 0

    if args.fix_values:
        print(f"\n{'=' * 50}")
        print("  FIXING INVALID VALUES")
        print(f"{'=' * 50}\n")

        fix_stats = pipeline.vector_store.fix_invalid_values()

        print("\n✓ Value fixes complete!")
        print(f"  Total documents: {fix_stats['total_documents']}")
        print(f"  Yield fixes: {fix_stats['yield_fixes']}")
        print(f"  Payout ratio fixes: {fix_stats['payout_fixes']}")
        return 0

    if args.stats:
        db_stats = pipeline.get_stats()
        print("\n=== Vector Database Statistics ===")
        print(f"Total documents: {db_stats.get('total_documents', 0)}")

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
            streak_yrs = doc.dividend_streak_years or 0
            yld = f"{doc.dividend_yield:.2f}%" if doc.dividend_yield else "N/A"
            print(f"👑 {doc.symbol:6} {doc.name[:30]:30} | {streak_yrs:2}yr | {yld}")

        return 0

    if args.export:
        count = pipeline.export_database(args.export)
        print(f"Exported {count} documents to {args.export}")
        return 0

    if args.import_file:
        count = pipeline.import_database(args.import_file)
        print(f"Imported {count} documents from {args.import_file}")
        return 0

    if args.import_url:
        direct_url = google_drive_direct_download_url(args.import_url)
        with NamedTemporaryFile(
            prefix="dividendscope_snapshot_", suffix=".json", delete=False
        ) as tmp:
            tmp_path = Path(tmp.name)

        print(f"Downloading snapshot from URL...\n{direct_url}")
        response = requests.get(direct_url, timeout=60)
        response.raise_for_status()
        tmp_path.write_bytes(response.content)

        count = pipeline.import_database(str(tmp_path))
        print(f"Imported {count} documents from remote snapshot")
        print(f"Temporary file: {tmp_path}")
        return 0

    if args.export_snapshot:
        count = pipeline.export_database(args.export_snapshot)
        print(f"Exported {count} documents to snapshot {args.export_snapshot}")
        print("Upload this file to your Google Drive link target manually.")
        return 0

    if args.add_symbols:
        symbols_to_add = [s.strip().upper() for s in args.add_symbols.split(",") if s.strip()]
        print(
            f"\nAdding {len(symbols_to_add)} symbol(s) from yfinance: {', '.join(symbols_to_add)}"
        )

        def progress_cb_add(msg: str, current: int, total: int) -> None:
            pct = (current / total) * 100 if total > 0 else 0
            print(f"\r[{pct:5.1f}%] {msg}...", end="", flush=True)

        add_stats = pipeline.add_symbols_from_yfinance(
            symbols_to_add, progress_callback=progress_cb_add
        )
        print()
        print(f"  Added: {add_stats.get('added', 0)}")
        print(f"  Errors: {add_stats.get('errors', 0)}")
        print(f"  Total documents in DB: {add_stats.get('total_documents', 0)}")
        return 0

    if args.file:
        file_res = pipeline.process_single_file(args.file)
        print(f"\nProcessed {file_res[0]} stocks: {', '.join(file_res[1])}")
        return 0

    # Handle enrich-existing action
    if args.enrich_existing:
        print(f"\n{'=' * 50}")
        print("  ENRICHING EXISTING DOCUMENTS")
        print(f"{'=' * 50}\n")

        enrich_symbols = args.symbols.split(",") if args.symbols else None

        def progress_cb_enrich(msg: str, current: int, total: int) -> None:
            pct = (current / total) * 100 if total > 0 else 0
            print(f"\r[{pct:5.1f}%] {msg}...", end="", flush=True)

        enrich_stats = pipeline.enrich_existing(
            symbols=enrich_symbols,
            progress_callback=progress_cb_enrich,
        )

        print("\n")
        print("Enrichment complete!")
        print(f"  Documents enriched: {enrich_stats.get('enriched', 0)}")
        print(f"  Errors: {enrich_stats.get('errors', 0)}")
        print(f"  Total documents: {enrich_stats.get('total_documents', 0)}")
        return 0

    # Run full pipeline
    sources = None if args.source == "all" else [args.source]

    print(f"\n{'=' * 50}")
    print("  DIVIDEND KINGS DATA INGESTION PIPELINE")
    print(f"{'=' * 50}\n")

    print(f"Data directory: {args.data_dir}")
    print(f"Database directory: {args.db_dir}")
    print(f"Sources: {args.source}")
    print(f"Merge strategy: {args.merge_strategy}")
    print(f"Enrich with yfinance: {args.enrich}")
    print()

    # Check if data exists
    data_path = Path(args.data_dir)
    if not data_path.exists() or not any(data_path.iterdir()):
        print("⚠️  No data files found!")
        print()
        print("To get started:")
        print("  1. Create sample files:  python ingest_data.py --create-samples")
        print("  2. Download real data from StockQuote.io and Nasdaq")
        print("  3. Place files in the appropriate directories:")
        print(f"     - StockQuote: {data_path}/stockquote/")
        print(f"     - Nasdaq: {data_path}/nasdaq/")
        print()
        return 1

    def progress_cb_run(msg: str, current: int, total: int) -> None:
        if args.enrich:
            pct = (current / total) * 100 if total > 0 else 0
            print(f"\r[{pct:5.1f}%] {msg}...", end="", flush=True)

    # Run ingestion
    run_stats = pipeline.run(
        sources=sources,
        merge_strategy=args.merge_strategy,
        enrich_with_yfinance=args.enrich,
        progress_callback=progress_cb_run if args.enrich else None,
    )

    if args.enrich:
        print()  # New line after progress

    # Print results
    print("\n" + "=" * 50)
    print("  INGESTION COMPLETE")
    print("=" * 50 + "\n")

    print("Statistics:")
    for key, value in sorted(run_stats.items()):
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
