#!/usr/bin/env python3
"""Compare stored dividend receipts against IBKR quarterly and annual reference totals."""

from __future__ import annotations

import argparse
import sys
from datetime import date

from services.portfolio_context import create_portfolio_context
from services.portfolio_dividend_quarters import (
    IBKR_REFERENCE_QUARTERLY_GROSS,
    IBKR_REFERENCE_THROUGH_DATE,
    compare_annual_net,
    compare_quarterly_gross,
    quarterly_gross_from_receipt_store,
)


def _parse_through(value: str | None) -> date:
    if not value:
        return IBKR_REFERENCE_THROUGH_DATE
    return date.fromisoformat(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1.0,
        help="Allowed absolute USD difference per period (default: 1.0)",
    )
    parser.add_argument(
        "--through",
        type=str,
        default=None,
        help="Include receipts through this date (YYYY-MM-DD); default: broker reference cutoff",
    )
    parser.add_argument(
        "--annual-only",
        action="store_true",
        help="Validate annual net totals only",
    )
    parser.add_argument(
        "--quarterly-only",
        action="store_true",
        help="Validate quarterly gross totals only",
    )
    args = parser.parse_args()
    through = _parse_through(args.through)
    validate_quarterly = not args.annual_only
    validate_annual = not args.quarterly_only

    ctx = create_portfolio_context()
    mismatches = 0

    if validate_quarterly:
        computed_q = quarterly_gross_from_receipt_store(ctx.receipts)
        if not computed_q and not validate_annual:
            print("No dividend receipts found — import IBKR activity first.", file=sys.stderr)
            return 1
        quarterly_rows = compare_quarterly_gross(
            computed_q,
            IBKR_REFERENCE_QUARTERLY_GROSS,
            tolerance_usd=args.tolerance,
        )
        print("Quarterly gross (payment date)")
        header = (
            f"{'Year':>6} {'Qtr':>4} {'IBKR ref':>12} {'Computed':>12} {'Delta':>10} {'Status':>10}"
        )
        print(header)
        print("-" * 58)
        for quarter_row in quarterly_rows:
            print(
                f"{quarter_row.year:>6} Q{quarter_row.quarter} "
                f"${quarter_row.reference_usd:>10,.2f} ${quarter_row.computed_usd:>10,.2f} "
                f"${quarter_row.delta_usd:>8,.2f} {quarter_row.status:>10}"
            )
            if quarter_row.status == "mismatch":
                mismatches += 1
        print()

    if validate_annual:
        computed_a = ctx.receipts.yearly_net_totals(through=through)
        if not computed_a:
            print("No dividend receipts found — import IBKR activity first.", file=sys.stderr)
            return 1
        annual_rows = compare_annual_net(
            computed_a,
            tolerance_usd=args.tolerance,
            through=through,
        )
        print(f"Annual net through {through.isoformat()}")
        print(f"{'Year':>6} {'IBKR ref':>12} {'Computed':>12} {'Delta':>10} {'Status':>10}")
        print("-" * 54)
        for annual_row in annual_rows:
            print(
                f"{annual_row.year:>6} "
                f"${annual_row.reference_usd:>10,.2f} ${annual_row.computed_usd:>10,.2f} "
                f"${annual_row.delta_usd:>8,.2f} {annual_row.status:>10}"
            )
            if annual_row.status == "mismatch":
                mismatches += 1

    print("-" * 54)
    if mismatches:
        print(f"FAILED: {mismatches} period(s) outside ${args.tolerance:.2f} tolerance.")
        return 1
    print("OK: all periods within tolerance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
