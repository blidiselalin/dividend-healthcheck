#!/usr/bin/env python3
"""
Migrate local SQLite + ChromaDB files into PostgreSQL.

Usage (on VM with Docker Postgres running):
  docker compose exec -T dividendscope python scripts/migrate_to_cloud_sql.py --data-dir /data

From host with DATABASE_URL:
  export DATABASE_URL=postgresql://dividendscope:pass@127.0.0.1:5432/dividendscope
  python scripts/migrate_to_cloud_sql.py
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _import_users(data_dir: Path) -> int:
    from auth.user_store import _parse_dt
    from db.connection import ensure_schema, get_connection, use_cloud_sql

    if not use_cloud_sql():
        raise RuntimeError("DATABASE_URL must be set")

    ensure_schema()
    users_db = data_dir / "users.db"
    if not users_db.is_file():
        return 0

    count = 0
    with sqlite3.connect(users_db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM users").fetchall()
    with get_connection() as pg:
        for row in rows:
            pg.execute(
                """
                INSERT INTO users (
                  id, email, name, picture_url, created_at, last_login_at, is_active, is_admin
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                  email = EXCLUDED.email,
                  name = EXCLUDED.name,
                  picture_url = EXCLUDED.picture_url,
                  last_login_at = EXCLUDED.last_login_at,
                  is_active = EXCLUDED.is_active,
                  is_admin = EXCLUDED.is_admin
                """,
                (
                    row["id"],
                    row["email"],
                    row["name"],
                    row["picture_url"],
                    _parse_dt(row["created_at"]),
                    _parse_dt(row["last_login_at"]),
                    bool(row["is_active"]),
                    bool(row["is_admin"]),
                ),
            )
            count += 1

        if (data_dir / "users.db").is_file():
            with sqlite3.connect(data_dir / "users.db") as conn:
                conn.row_factory = sqlite3.Row
                for row in conn.execute("SELECT * FROM access_requests").fetchall():
                    pg.execute(
                        """
                        INSERT INTO access_requests (
                          email, user_id, name, picture_url, status, message,
                          requested_at, reviewed_at, reviewed_by
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (email) DO UPDATE SET
                          status = EXCLUDED.status,
                          reviewed_at = EXCLUDED.reviewed_at,
                          reviewed_by = EXCLUDED.reviewed_by
                        """,
                        (
                            row["email"],
                            row["user_id"],
                            row["name"],
                            row["picture_url"],
                            row["status"],
                            row["message"],
                            _parse_dt(row["requested_at"]),
                            _parse_dt(row["reviewed_at"]),
                            row["reviewed_by"],
                        ),
                    )
    return count


def _import_portfolio_db(db_path: Path, user_id: str) -> dict:
    from db.connection import ensure_schema, get_connection

    ensure_schema()
    stats = {"holdings": 0, "journal": 0, "deposits": 0, "dividends": 0}
    if not db_path.is_file():
        return stats

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        with get_connection() as pg:
            pg.execute(
                """
                INSERT INTO users (id, email, name, created_at, last_login_at, is_active, is_admin)
                VALUES (%s, %s, %s, now(), now(), TRUE, FALSE)
                ON CONFLICT (id) DO NOTHING
                """,
                (user_id, f"{user_id}@users.local", user_id),
            )
            for row in conn.execute("SELECT * FROM holdings").fetchall():
                pg.execute(
                    """
                    INSERT INTO holdings (
                      user_id, symbol, shares, avg_cost_per_share, acquisition_value,
                      commission, dividends_paid, estimated_avg_price, sort_order, company_name
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (user_id, symbol) DO UPDATE SET
                      shares = EXCLUDED.shares,
                      avg_cost_per_share = EXCLUDED.avg_cost_per_share,
                      acquisition_value = EXCLUDED.acquisition_value
                    """,
                    (
                        user_id,
                        row["symbol"],
                        row["shares"],
                        row["avg_cost_per_share"],
                        row["acquisition_value"],
                        row["commission"],
                        row["dividends_paid"],
                        row["estimated_avg_price"],
                        row["sort_order"],
                        row["company_name"],
                    ),
                )
                stats["holdings"] += 1
            for row in conn.execute("SELECT * FROM purchase_journal").fetchall():
                pg.execute(
                    """
                    INSERT INTO purchase_journal (user_id, symbol, purchase_date, price_usd)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id, symbol, purchase_date, price_usd) DO NOTHING
                    """,
                    (user_id, row["symbol"], row["purchase_date"], row["price_usd"]),
                )
                stats["journal"] += 1
            for row in conn.execute("SELECT * FROM monthly_deposits").fetchall():
                pg.execute(
                    """
                    INSERT INTO monthly_deposits (
                      user_id, period_key, year, month, label,
                      deposit_eur, deposit_usd, portfolio_eur, sort_order
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (user_id, period_key) DO NOTHING
                    """,
                    (
                        user_id,
                        row["period_key"],
                        row["year"],
                        row["month"],
                        row["label"],
                        row["deposit_eur"],
                        row["deposit_usd"],
                        row["portfolio_eur"],
                        row["sort_order"],
                    ),
                )
                stats["deposits"] += 1
            for row in conn.execute("SELECT * FROM net_dividends").fetchall():
                pg.execute(
                    """
                    INSERT INTO net_dividends (user_id, period_key, year, month, net_usd)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, period_key) DO NOTHING
                    """,
                    (user_id, row["period_key"], row["year"], row["month"], row["net_usd"]),
                )
                stats["dividends"] += 1
    return stats


def _import_market_library(data_dir: Path) -> int:
    from data_ingestion.vector_store import VectorStore
    from db.postgres_market_store import PostgresMarketStore

    store = VectorStore(persist_directory=str(data_dir / "vectordb"))
    if getattr(store, "_use_postgres", False):
        return 0
    documents = store.get_all_documents()
    if not documents:
        return 0
    pg = PostgresMarketStore()
    pg.add_documents(documents)
    return len(documents)


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate local files to PostgreSQL")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path.home() / ".dividendscope" / "data",
    )
    args = parser.parse_args()
    data_dir = args.data_dir.expanduser()

    print(f"Migrating from {data_dir}")
    users = _import_users(data_dir)
    print(f"  users/access: {users} user rows")

    total = {"holdings": 0, "journal": 0, "deposits": 0, "dividends": 0}
    legacy = data_dir / "portfolio.db"
    if legacy.is_file():
        stats = _import_portfolio_db(legacy, "legacy-local")
        for key in total:
            total[key] += stats[key]
        print(f"  legacy portfolio: {stats}")

    users_dir = data_dir / "users"
    if users_dir.is_dir():
        for user_dir in sorted(users_dir.iterdir()):
            db_path = user_dir / "portfolio.db"
            if not db_path.is_file():
                continue
            stats = _import_portfolio_db(db_path, user_dir.name)
            for key in total:
                total[key] += stats[key]
            print(f"  user {user_dir.name}: {stats}")

    market = _import_market_library(data_dir)
    print(f"  market library: {market} symbols")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
