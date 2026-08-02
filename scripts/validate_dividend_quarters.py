#!/usr/bin/env python3
"""Compare stored dividend receipts against IBKR quarterly reference totals."""

from __future__ import annotations

import argparse
import sys

from services.portfolio_context import create_portfolio_context
from services.portfolio_dividend_quarters import (
    IBKR_REFERENCE_QUARTERLY_GROSS,
    compare_quarterly_gross,
    quarterly_gross_from_receipt_store,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1.0,
        help="Allowed absolute USD difference per quarter (default: 1.0)",
    )
    args = parser.parse_args()

    ctx = create_portfolio_context()
    computed = quarterly_gross_from_receipt_store(ctx.receipts)
    if not computed:
        print("No dividend receipts found — import IBKR activity first.", file=sys.stderr)
        return 1

    rows = compare_quarterly_gross(
        computed,
        IBKR_REFERENCE_QUARTERLY_GROSS,
        tolerance_usd=args.tolerance,
    )

    print(f"{'Year':>6} {'Qtr':>4} {'IBKR ref':>12} {'Computed':>12} {'Delta':>10} {'Status':>10}")
    print("-" * 58)
    mismatches = 0
    for row in rows:
        print(
            f"{row.year:>6} Q{row.quarter} "
            f"${row.reference_usd:>10,.2f} ${row.computed_usd:>10,.2f} "
            f"${row.delta_usd:>8,.2f} {row.status:>10}"
        )
        if row.status == "mismatch":
            mismatches += 1

    print("-" * 58)
    if mismatches:
        print(f"FAILED: {mismatches} quarter(s) outside ${args.tolerance:.2f} tolerance.")
        return 1
    print("OK: all complete quarters within tolerance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
