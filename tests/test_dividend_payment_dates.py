"""Dividend payment date enrichment and receipt reconciliation."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from data_ingestion.dividend_receipt_store import DividendReceiptStore
from data_ingestion.models import DividendRecord, StockDocument
from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore
from services.dividend_payment_dates import (
    clear_payment_date_cache,
    enrich_document_payment_dates,
    payment_date_for_record,
    reconcile_receipt_dates,
)
from services.portfolio_context import create_portfolio_context


def test_payment_date_for_record_uses_payment_date_when_set() -> None:
    record = DividendRecord(
        ex_date=date(2026, 6, 10),
        payment_date=date(2026, 6, 28),
        amount=0.48,
    )
    assert payment_date_for_record(record) == date(2026, 6, 28)


def test_enrich_document_applies_local_csv_payment_dates(tmp_path: Path) -> None:
    csv_path = tmp_path / "KO_dividends.csv"
    csv_path.write_text(
        "ex_date,payment_date,amount\n"
        "2026-06-10,2026-06-27,0.485\n",
        encoding="utf-8",
    )
    doc = StockDocument(
        symbol="KO",
        name="Coca-Cola",
        dividend_history=[
            DividendRecord(
                ex_date=date(2026, 6, 10),
                payment_date=None,
                amount=0.485,
            ),
        ],
    )

    with patch("config.DOWNLOADS_DIR", tmp_path):
        clear_payment_date_cache()
        enriched = enrich_document_payment_dates(
            "KO",
            doc,
            fetch_nasdaq=False,
            reference_date=date(2026, 6, 19),
        )

    assert enriched is not None
    assert enriched.dividend_history[0].payment_date == date(2026, 6, 27)


def test_enrich_document_uses_median_lag_when_only_ex_matches(tmp_path: Path) -> None:
    csv_path = tmp_path / "KO_dividends.csv"
    csv_path.write_text(
        "ex_date,payment_date,amount\n"
        "2026-03-10,2026-03-28,0.485\n"
        "2025-12-10,2025-12-27,0.485\n"
        "2025-09-10,2025-09-26,0.485\n",
        encoding="utf-8",
    )
    doc = StockDocument(
        symbol="KO",
        name="Coca-Cola",
        dividend_history=[
            DividendRecord(
                ex_date=date(2026, 6, 10),
                payment_date=None,
                amount=0.485,
            ),
        ],
    )

    with patch("config.DOWNLOADS_DIR", tmp_path):
        clear_payment_date_cache()
        enriched = enrich_document_payment_dates(
            "KO",
            doc,
            fetch_nasdaq=False,
            reference_date=date(2026, 6, 19),
        )

    assert enriched is not None
    # Median lag from CSV samples is 17 days (28-10, 27-10, 26-10 → 17).
    assert enriched.dividend_history[0].payment_date == date(2026, 6, 27)


def test_enrich_document_applies_nasdaq_payment_dates() -> None:
    from services.dividend_payment_dates import PaymentDateLookup

    doc = StockDocument(
        symbol="KO",
        name="Coca-Cola",
        dividend_history=[
            DividendRecord(
                ex_date=date(2026, 6, 10),
                payment_date=None,
                amount=0.485,
            ),
        ],
    )
    lookup = PaymentDateLookup()
    lookup.by_ex_amount[(date(2026, 6, 10), 0.485)] = date(2026, 6, 27)
    lookup.by_ex[date(2026, 6, 10)] = date(2026, 6, 27)

    with patch(
        "services.dividend_payment_dates._build_payment_date_lookup",
        return_value=lookup,
    ):
        clear_payment_date_cache()
        enriched = enrich_document_payment_dates(
            "KO",
            doc,
            fetch_nasdaq=True,
            reference_date=date(2026, 6, 19),
        )

    assert enriched is not None
    assert enriched.dividend_history[0].payment_date == date(2026, 6, 27)


def test_sync_receipt_updates_pay_date(tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "portfolio.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE holdings (symbol TEXT PRIMARY KEY)")
    store = DividendReceiptStore(db)
    store.sync_receipt(
        "KO",
        ex_date=date(2026, 6, 10),
        pay_date=date(2026, 6, 24),
        per_share_usd=0.485,
        shares_held=10.0,
        gross_usd=4.85,
    )
    outcome = store.sync_receipt(
        "KO",
        ex_date=date(2026, 6, 10),
        pay_date=date(2026, 6, 28),
        per_share_usd=0.485,
        shares_held=10.0,
        gross_usd=4.85,
    )
    assert outcome == "updated"
    rows = store.list_for_symbol("KO")
    assert len(rows) == 1
    assert rows[0].pay_date == date(2026, 6, 28)


def test_reconcile_fixes_stale_pay_dates(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    portfolio = PortfolioStore(db_path=db, seed=False)
    journal = PurchaseJournalStore(db_path=db, seed=False)
    portfolio.upsert_holding("KO", shares=10, avg_cost_per_share=50.0)
    journal.add_purchase("KO", date(2024, 1, 1), 48.0)

    doc = StockDocument(
        symbol="KO",
        name="Coca-Cola",
        dividend_history=[
            DividendRecord(
                ex_date=date(2026, 6, 10),
                payment_date=date(2026, 6, 28),
                amount=0.485,
            ),
        ],
        payment_frequency=4,
        annual_dividend=1.94,
    )

    ctx = create_portfolio_context(db_path=db)
    receipt_store = DividendReceiptStore(db)
    receipt_store.sync_receipt(
        "KO",
        ex_date=date(2026, 6, 10),
        pay_date=date(2026, 6, 24),
        per_share_usd=0.485,
        shares_held=10.0,
        gross_usd=4.85,
    )

    documents = {"KO": doc}
    stats = reconcile_receipt_dates(
        ctx,
        portfolio.list_holdings(),
        documents,
        fetch_nasdaq=False,
        reference_date=date(2026, 6, 30),
    )

    assert stats.receipts_updated >= 1
    assert stats.pay_dates_corrected >= 1
    fixed = receipt_store.list_for_symbol("KO")[0]
    assert fixed.pay_date == date(2026, 6, 28)
