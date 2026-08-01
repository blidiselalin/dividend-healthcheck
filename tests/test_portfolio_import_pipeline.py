"""Tests for portfolio import validation/normalization pipeline."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from services.ibkr_activity_parser import parse_activity_statement_csv
from services.portfolio_broker_import_service import ImportMode, apply_import
from services.portfolio_context import create_portfolio_context
from services.portfolio_import_pipeline import (
    content_fingerprint,
    detect_in_statement_duplicates,
    normalize_statement,
    prepare_statement,
    validate_stored_deposit_currency_pairs,
    validate_stored_deposits_against_statement,
)
from services.portfolio_timeline_service import (
    fill_missing_deposit_months,
    trim_pre_inception_deposits,
)


def test_content_fingerprint_is_stable() -> None:
    text = "Statement,Data,Title,Activity Statement\n"
    assert content_fingerprint(text) == content_fingerprint(text)
    assert content_fingerprint(text) != content_fingerprint(text + "\n")


def test_normalize_statement_rounds_money_fields(sample_csv: str) -> None:
    statement = normalize_statement(parse_activity_statement_csv(sample_csv))
    trade = statement.trades[0]
    assert trade.price_usd == round(trade.price_usd, 2)
    assert trade.quantity == round(trade.quantity, 4)


def test_detect_duplicate_trades_in_same_file() -> None:
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        "Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,"
        "Quantity,T. Price,Proceeds,Comm/Fee,Basis,Realized P/L,MTM P/L,Code\n"
        "Trades,Data,Order,Stocks,USD,AAPL,2024-01-15,10,150,1500,1,0,0,0,O\n"
        "Trades,Data,Order,Stocks,USD,AAPL,2024-01-15,10,150,1500,1,0,0,0,O\n"
    )
    statement = parse_activity_statement_csv(csv_text)
    issues = detect_in_statement_duplicates(statement)
    assert any("duplicate trade" in issue.message.lower() for issue in issues)


def test_prepare_statement_flags_extreme_deposit() -> None:
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        "Deposits & Withdrawals,Data,USD,2024-01-01,Electronic Fund Transfer,500000\n"
    )
    _statement, issues, _fp = prepare_statement(csv_text)
    assert any("unusually large deposit" in issue.message.lower() for issue in issues)


def test_fill_missing_deposit_months_inserts_zero_rows(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    ctx = create_portfolio_context(db_path=db)
    ctx.deposits.upsert_deposit(
        year=2024,
        month=1,
        label="January 2024",
        deposit_eur=1000.0,
        deposit_usd=1100.0,
        portfolio_eur=10000.0,
    )
    ctx.deposits.upsert_deposit(
        year=2024,
        month=3,
        label="March 2024",
        deposit_eur=500.0,
        deposit_usd=550.0,
        portfolio_eur=10800.0,
    )

    added, issues = fill_missing_deposit_months(
        ctx,
        range_end=date(2024, 3, 1),
    )
    assert added == 1
    assert any("Filled 1 missing" in issue.message for issue in issues)

    rows = ctx.deposits.list_deposits()
    feb = next(item for item in rows if item.period.month == 2)
    assert feb.deposit_eur == 0.0
    assert feb.portfolio_eur == 0.0


def test_import_fills_calendar_gaps_after_replace(tmp_path: Path, sample_csv: str) -> None:
    db = tmp_path / "portfolio.db"
    result = apply_import(sample_csv, mode=ImportMode.REPLACE, db_path=db)
    assert result.months_filled >= 0

    ctx = create_portfolio_context(db_path=db)
    keys = [item.period_key for item in ctx.deposits.list_deposits()]
    assert keys == sorted(keys)
    assert len(keys) == len(set(keys))
    assert "2025-01" not in keys
    assert "2025-02" in keys
    assert "2025-12" in keys


def test_validate_stored_deposits_allows_merge_accumulation(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    ctx = create_portfolio_context(db_path=db)
    ctx.deposits.upsert_deposit(
        year=2026,
        month=5,
        label="May 2026",
        deposit_eur=17452.07,
        deposit_usd=4169.35,
        portfolio_eur=0.0,
    )
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        'Statement,Data,Period,"May 1, 2026 - May 31, 2026"\n'
        "Account Information,Data,Base Currency,EUR\n"
        "Deposits & Withdrawals,Header,Currency,Settle Date,Description,Amount\n"
        "Deposits & Withdrawals,Data,USD,2026-05-06,Electronic Fund Transfer,4000\n"
        "Deposits & Withdrawals,Data,Total,,,4000\n"
        "Deposits & Withdrawals,Data,Total in EUR,,,16752\n"
    )
    statement = parse_activity_statement_csv(csv_text)
    issues = validate_stored_deposits_against_statement(
        ctx.deposits.list_deposits(),
        statement,
        merge_mode=True,
    )
    assert issues == []


def test_validate_stored_deposits_flags_under_import_on_replace(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    ctx = create_portfolio_context(db_path=db)
    ctx.deposits.upsert_deposit(
        year=2026,
        month=5,
        label="May 2026",
        deposit_eur=100.0,
        deposit_usd=110.0,
        portfolio_eur=0.0,
    )
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        "Account Information,Data,Base Currency,EUR\n"
        "Deposits & Withdrawals,Header,Currency,Settle Date,Description,Amount\n"
        "Deposits & Withdrawals,Data,EUR,2026-05-11,Electronic Fund Transfer,700.07\n"
        "Deposits & Withdrawals,Data,Total,,,700.07\n"
    )
    statement = parse_activity_statement_csv(csv_text)
    issues = validate_stored_deposits_against_statement(
        ctx.deposits.list_deposits(),
        statement,
        merge_mode=False,
    )
    assert any("stored deposit €" in issue.message for issue in issues)


def test_trim_pre_inception_deposits_removes_zero_deposit_leadin(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    ctx = create_portfolio_context(db_path=db)
    ctx.deposits.upsert_deposit(
        year=2025,
        month=1,
        label="January 2025",
        deposit_eur=0.0,
        deposit_usd=0.0,
        portfolio_eur=0.0,
    )
    ctx.deposits.upsert_deposit(
        year=2025,
        month=2,
        label="February 2025",
        deposit_eur=1000.0,
        deposit_usd=1100.0,
        portfolio_eur=0.0,
    )
    removed, issues = trim_pre_inception_deposits(ctx)
    assert removed == 1
    keys = [item.period_key for item in ctx.deposits.list_deposits()]
    assert keys == ["2025-02"]
    assert any("Removed 1 month" in issue.message for issue in issues)


def test_validate_stored_deposit_currency_pairs_flags_mismatch() -> None:
    from data_ingestion.deposits_store import MonthlyDeposit

    rows = [
        MonthlyDeposit(
            period=date(2025, 1, 1),
            label="January 2025",
            deposit_eur=1000.0,
            deposit_usd=500.0,
            portfolio_eur=0.0,
            sort_order=1,
        ),
        MonthlyDeposit(
            period=date(2025, 2, 1),
            label="February 2025",
            deposit_eur=920.0,
            deposit_usd=1000.0,
            portfolio_eur=0.0,
            sort_order=2,
        ),
    ]
    issues = validate_stored_deposit_currency_pairs(rows)
    assert any("FX-consistent" in issue.message for issue in issues)


@pytest.fixture
def sample_csv() -> str:
    fixture = Path(__file__).resolve().parent / "fixtures" / "ibkr_activity_sample.csv"
    return fixture.read_text(encoding="utf-8")
