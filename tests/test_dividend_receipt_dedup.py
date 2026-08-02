"""Regression tests for dividend receipt deduplication and filtered totals."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from data_ingestion.dividend_receipt_store import DividendReceiptStore
from data_ingestion.dividend_transaction import DividendDedupInput, build_dedup_key
from services.dividend_receipt_dedup_service import reconcile_dividend_receipts
from services.ibkr_activity_parser import build_canonical_dividends, parse_activity_statement_csv
from services.portfolio_broker_import_service import ImportMode, apply_import


def _dividend_csv(*rows: str) -> str:
    header = (
        "Statement,Data,Title,Activity Statement\n"
        "Account Information,Data,Account,U15587745\n"
        "Open Positions,Data,Summary,Stocks,USD,KO,10,60,60,600\n"
    )
    return header + "\n".join(rows) + "\n"


def test_build_dedup_key_stable_without_filename() -> None:
    payload = DividendDedupInput(
        broker_account="U15587745",
        broker_transaction_id=None,
        symbol="KO",
        isin="US123",
        pay_date=date(2025, 3, 15),
        currency="USD",
        gross_usd=10.0,
        withholding_usd=1.0,
        net_usd=9.0,
    )
    assert build_dedup_key(payload) == build_dedup_key(payload)


def test_import_same_file_twice_is_idempotent(tmp_path: Path) -> None:
    csv_text = _dividend_csv(
        'Dividends,Data,USD,2025-03-15,"KO(US123) Cash Dividend USD 0.50 per Share",5.00',
        'Withholding Tax,Data,USD,2025-03-15,"KO(US123) Withholding @ 10% on Dividend",-0.50',
    )
    db = tmp_path / "portfolio.db"
    first = apply_import(csv_text, mode=ImportMode.REPLACE, db_path=db)
    second = apply_import(csv_text, mode=ImportMode.MERGE, db_path=db)

    assert first.dividend_rows_inserted == 1
    assert second.dividend_rows_duplicates == 1
    assert second.dividend_rows_inserted == 0

    store = DividendReceiptStore(db)
    assert len(store.list_for_symbol("KO")) == 1
    receipt = store.list_for_symbol("KO")[0]
    assert receipt.gross_usd == 5.0
    assert receipt.withholding_usd == 0.5
    assert receipt.net_usd == 4.5


def test_overlapping_exports_do_not_duplicate(tmp_path: Path) -> None:
    csv_full = _dividend_csv(
        'Dividends,Data,USD,2025-03-15,"KO(US123) Cash Dividend USD 0.50 per Share",5.00',
        'Dividends,Data,USD,2025-06-15,"KO(US123) Cash Dividend USD 0.55 per Share",5.50',
    )
    csv_overlap = _dividend_csv(
        'Dividends,Data,USD,2025-06-15,"KO(US123) Cash Dividend USD 0.55 per Share",5.50',
        'Dividends,Data,USD,2025-09-15,"KO(US123) Cash Dividend USD 0.60 per Share",6.00',
    )
    db = tmp_path / "portfolio.db"
    apply_import(csv_full, mode=ImportMode.REPLACE, db_path=db)
    second = apply_import(csv_overlap, mode=ImportMode.MERGE, db_path=db)

    assert second.dividend_rows_duplicates == 1
    assert second.dividend_rows_inserted == 1

    store = DividendReceiptStore(db)
    assert store.yearly_net_totals()[2025] == pytest.approx(16.5)


def test_reversal_and_forecast_rows_excluded(tmp_path: Path) -> None:
    csv_text = _dividend_csv(
        'Dividends,Data,USD,2025-03-15,"KO(US123) Cash Dividend USD 0.50 per Share",5.00',
        "Dividends,Data,USD,2025-03-16,"
        '"KO(US123) Cash Dividend USD 0.50 per Share (Reversal)",-5.00',
        'Dividends,Data,USD,2025-04-15,"KO(US123) Forecast Dividend USD 0.50 per Share",5.00',
    )
    db = tmp_path / "portfolio.db"
    result = apply_import(csv_text, mode=ImportMode.REPLACE, db_path=db)
    assert result.dividend_rows_inserted == 1
    assert result.dividend_rows_rejected >= 2

    store = DividendReceiptStore(db)
    assert store.monthly_net_totals()[(2025, 3)] == pytest.approx(5.0)


def test_withholding_combined_into_net(tmp_path: Path) -> None:
    csv_text = _dividend_csv(
        'Dividends,Data,USD,2025-05-20,"PEP(US123) Cash Dividend USD 1.00 per Share",10.00',
        'Withholding Tax,Data,USD,2025-05-20,"PEP(US123) Withholding @ 15% on Dividend",-1.50',
    )
    db = tmp_path / "portfolio.db"
    apply_import(csv_text, mode=ImportMode.REPLACE, db_path=db)
    store = DividendReceiptStore(db)
    receipt = store.list_for_symbol("PEP")[0]
    assert receipt.gross_usd == 10.0
    assert receipt.withholding_usd == 1.5
    assert receipt.net_usd == 8.5


def test_computed_rows_excluded_from_posted_totals(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    store = DividendReceiptStore(db)
    store.upsert_broker_receipt(
        symbol="KO",
        ex_date=date(2025, 3, 15),
        pay_date=date(2025, 3, 15),
        per_share_usd=0.5,
        shares_held=10.0,
        gross_usd=5.0,
        withholding_usd=0.5,
        net_usd=4.5,
        dedup_key="broker-ko-mar",
        dividend_type="actual",
    )
    store.sync_receipt(
        "KO",
        ex_date=date(2025, 3, 14),
        pay_date=date(2025, 3, 15),
        per_share_usd=0.5,
        shares_held=10.0,
        gross_usd=5.0,
        source="computed",
    )
    assert store.monthly_gross_totals()[(2025, 3)] == pytest.approx(5.0)


def test_dedupe_marks_duplicate_rows_excluded(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    store = DividendReceiptStore(db)
    key = build_dedup_key(
        DividendDedupInput(
            broker_account="U1",
            broker_transaction_id=None,
            symbol="KO",
            isin=None,
            pay_date=date(2025, 3, 15),
            currency="USD",
            gross_usd=5.0,
            withholding_usd=0.0,
            net_usd=5.0,
        )
    )
    store._insert_receipt(
        "KO",
        ex_date=date(2025, 3, 15),
        pay_date=date(2025, 3, 15),
        per_share_usd=0.5,
        shares_held=10.0,
        gross_usd=5.0,
        source="ibkr",
        dedup_key=key,
    )
    store._insert_receipt(
        "KO",
        ex_date=date(2025, 3, 15),
        pay_date=date(2025, 3, 15),
        per_share_usd=0.5,
        shares_held=10.0,
        gross_usd=5.0,
        source="ibkr",
        dedup_key=key,
    )
    reconcile_dividend_receipts(store)
    rows = store.list_for_symbol("KO")
    assert len(rows) == 1
    assert store.monthly_gross_totals()[(2025, 3)] == pytest.approx(5.0)


def test_legitimate_same_day_two_payments(tmp_path: Path) -> None:
    csv_text = _dividend_csv(
        'Dividends,Data,USD,2025-07-10,"KO(US123) Cash Dividend USD 0.50 per Share",5.00',
        'Dividends,Data,USD,2025-07-10,"PEP(US456) Cash Dividend USD 1.00 per Share",8.00',
    )
    db = tmp_path / "portfolio.db"
    apply_import(csv_text, mode=ImportMode.REPLACE, db_path=db)
    store = DividendReceiptStore(db)
    assert store.monthly_gross_totals()[(2025, 7)] == pytest.approx(13.0)


def test_build_canonical_dividends_from_parser() -> None:
    statement = parse_activity_statement_csv(
        _dividend_csv(
            'Dividends,Data,USD,2025-03-15,"KO(US123) Cash Dividend USD 0.50 per Share",5.00',
        )
    )
    rows, rejected = build_canonical_dividends(statement)
    assert rejected == 0
    assert len(rows) == 1
    assert rows[0].net_usd == 5.0
