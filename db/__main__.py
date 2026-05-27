"""CLI: python -m db --migrate"""

from __future__ import annotations

import logging
import sys

from db.connection import ensure_schema, get_database_url, use_postgres_db


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    if "--migrate" in sys.argv:
        ensure_schema()
        print("Schema applied.")
        return 0
    print(f"postgres={use_postgres_db()} url={'set' if get_database_url() else 'unset'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
