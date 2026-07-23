"""Tests for portfolio import validation/normalization pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.ibkr_activity_parser import parse_activity_statement_csv
from services.portfolio_broker_import_service import ImportMode, apply_import
from services.portfolio_context import create_portfolio_context
from services.portfolio_import_pipeline import (
    content_fingerprint,
    detect_in_statement_duplicates,
    fill_missing_deposit_months,
    normalize_statement,
    prepare_statement,
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

    added, issues = fill_missing_deposit_months(ctx)
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
    months = [item.period.month for item in ctx.deposits.list_deposits()]
    assert months == sorted(months)
    if len(months) >= 2:
        assert months[-1] - months[0] + 1 == len(months)


@pytest.fixture
def sample_csv() -> str:
    fixture = Path(__file__).resolve().parent / "fixtures" / "ibkr_activity_sample.csv"
    return fixture.read_text(encoding="utf-8")
