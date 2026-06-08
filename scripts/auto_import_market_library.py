#!/usr/bin/env python3
"""
Auto-import legacy Chroma/fallback JSON into PostgreSQL on first boot.

Called from docker-entrypoint.sh unless DIVIDENDSCOPE_SKIP_LEGACY_IMPORT is set.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from config import DATA_DIR
    from services.market_library_migration import (
        diagnose_legacy_import,
        import_legacy_market_library,
        should_auto_import,
    )

    data_dir = Path(DATA_DIR)
    diag = diagnose_legacy_import(data_dir)
    print(f"Market library diagnostics: {diag.message}")

    if not should_auto_import(data_dir):
        return 0

    print("Auto-importing legacy vectordb into PostgreSQL stock_documents…")
    stats = import_legacy_market_library(data_dir, merge_with_postgres=True)
    print(stats.get("message", stats))
    return 0 if stats.get("errors", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
