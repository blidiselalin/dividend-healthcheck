#!/usr/bin/env python3
"""
Import Interactive Brokers Activity Statement CSV into portfolio storage.

Usage:
  python scripts/import_ibkr_activity.py statement.csv --dry-run
  python scripts/import_ibkr_activity.py statement.csv --mode merge
  python scripts/import_ibkr_activity.py statement.csv --mode replace --confirm
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Import IBKR Activity Statement CSV")
    parser.add_argument("csv_path", type=Path, help="Path to Activity Statement CSV")
    parser.add_argument(
        "--mode",
        choices=("merge", "replace"),
        default="merge",
        help="Merge updates CSV symbols only; replace wipes all portfolio data first",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only; do not write")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required with --mode replace (non-interactive safety)",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="SQLite portfolio file (tests/local); omit for Postgres user scope",
    )
    args = parser.parse_args()

    if not args.csv_path.is_file():
        print(f"File not found: {args.csv_path}", file=sys.stderr)
        return 1
    if args.mode == "replace" and not args.dry_run and not args.confirm:
        print("Replace mode requires --confirm", file=sys.stderr)
        return 1

    from services.ibkr_activity_parser import has_blocking_errors
    from services.portfolio_broker_import_service import ImportMode, apply_import, preview_import

    content = args.csv_path.read_text(encoding="utf-8-sig")
    preview = preview_import(content)

    print(f"Account: {preview.meta.account or '—'}")
    print(f"Period: {preview.meta.period or '—'}")
    print(
        f"Positions: {preview.position_count}  Stock trades: {preview.trade_count}  "
        f"Dividends: {preview.dividend_count}  Deposit months: {preview.deposit_month_count}"
    )
    if preview.forex_trades_skipped:
        print(f"FX trades skipped: {preview.forex_trades_skipped}")
    if preview.symbols:
        print("Symbols:", ", ".join(preview.symbols))
    for issue in preview.issues:
        prefix = issue.level.value.upper()
        print(f"[{prefix}] {issue.message}")

    if args.dry_run:
        if has_blocking_errors(preview.issues):
            return 2
        print("Dry run — no changes written.")
        return 0

    if has_blocking_errors(preview.issues):
        print("Import blocked by validation errors.", file=sys.stderr)
        return 2

    mode = ImportMode.REPLACE if args.mode == "replace" else ImportMode.MERGE
    result = apply_import(content, mode=mode, db_path=args.db_path)
    print(
        f"Applied ({result.mode.value}): holdings={result.holdings_upserted} "
        f"trades={result.trades_imported} dividends={result.dividends_imported} "
        f"deposits={result.deposits_imported}"
    )
    if result.cleared is not None:
        print(f"Cleared {result.cleared} rows before import.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
