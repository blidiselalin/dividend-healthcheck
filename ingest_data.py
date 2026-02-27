#!/usr/bin/env python3
"""
Data Ingestion CLI for Dividend Kings Analyzer.

Downloads and processes stock data from public sources into a vector database
for enhanced report generation.

Usage:
    # Run full ingestion from all sources
    python ingest_data.py
    
    # Process specific source only
    python ingest_data.py --source stockquote
    python ingest_data.py --source nasdaq
    
    # Process a single file
    python ingest_data.py --file data/downloads/stockquote/fundamentals.csv
    
    # Create sample data files (to see expected format)
    python ingest_data.py --create-samples
    
    # Search the database
    python ingest_data.py --search "high yield dividend king"
    
    # List all dividend kings in database
    python ingest_data.py --list-kings
    
    # Export database to JSON
    python ingest_data.py --export data/export.json
    
    # Import database from JSON
    python ingest_data.py --import data/export.json
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from data_ingestion.pipeline import DataIngestionPipeline, create_sample_data
from data_ingestion.vector_store import VectorStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


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
        help="Fix invalid/corrupt values (yields > 30%, payout > 500%)",
    )
    
    # Configuration
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data/downloads",
        help="Directory containing downloaded data (default: data/downloads)",
    )
    
    parser.add_argument(
        "--db-dir",
        type=str,
        default="data/vectordb",
        help="Directory for vector database (default: data/vectordb)",
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
