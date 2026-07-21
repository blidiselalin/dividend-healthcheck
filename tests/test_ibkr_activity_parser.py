"""Tests for IBKR Activity Statement CSV parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.ibkr_activity_parser import (
    ImportIssueLevel,
    has_blocking_errors,
    parse_activity_statement_csv,
    validate_statement,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ibkr_activity_sample.csv"


@pytest.fixture
def sample_csv() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parse_sample_statement(sample_csv: str) -> None:
    statement = parse_activity_statement_csv(sample_csv)
    assert statement.meta.account == "U15587745"
    assert len(statement.open_positions) == 2
    assert {p.symbol for p in statement.open_positions} == {"AAPL", "MSFT"}
    assert len(statement.trades) == 3
    sells = [t for t in statement.trades if t.side == "sell"]
    assert len(sells) == 1
    assert sells[0].symbol == "AAPL"
    assert sells[0].quantity == 3.0
    assert len(statement.dividends) == 2
    aapl_div = next(d for d in statement.dividends if d.symbol == "AAPL")
    assert aapl_div.per_share_usd == 0.25
    assert aapl_div.gross_usd == 2.50


def test_validate_sample_has_no_blocking_errors(sample_csv: str) -> None:
    statement = parse_activity_statement_csv(sample_csv)
    issues = validate_statement(statement)
    assert not has_blocking_errors(issues)


def test_validate_rejects_non_ibkr_file() -> None:
    statement = parse_activity_statement_csv("foo,bar\n")
    issues = validate_statement(statement)
    assert has_blocking_errors(issues)
    assert any(issue.level == ImportIssueLevel.ERROR for issue in issues)


def test_parse_dividend_with_spaced_symbol_and_ordinary_dividend_format() -> None:
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        "Open Positions,Data,Summary,Stocks,USD,SBUX,10,90,90,900\n"
        "Open Positions,Data,Summary,Stocks,USD,ARCC,20,18,18,360\n"
        "Dividends,Data,USD,2025-03-15,"
        '"SBUX (US8552441094) Cash Dividend USD 0.61 (Ordinary Dividend)",6.10\n'
        "Dividends,Data,USD,2025-06-15,"
        '"ARCC (US04010L1035) Cash Dividend USD 0.48 (Ordinary Dividend)",9.60\n'
    )
    statement = parse_activity_statement_csv(csv_text)

    assert not statement.issues
    assert len(statement.dividends) == 2
    sbux = next(d for d in statement.dividends if d.symbol == "SBUX")
    assert sbux.per_share_usd == 0.61
    assert sbux.gross_usd == 6.10
    arcc = next(d for d in statement.dividends if d.symbol == "ARCC")
    assert arcc.per_share_usd == 0.48
    assert arcc.gross_usd == 9.60


def test_parse_skips_forex_trades() -> None:
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        "Open Positions,Data,Summary,Stocks,USD,KO,10,60,60,600\n"
        'Trades,Data,Order,Stocks,USD,KO,"2025-02-13, 09:30:00",10,60,600,USD,-1\n'
        'Trades,Data,Order,Forex,USD,EUR.USD,"2025-01-13, 09:30:44",-446.15,1.01892,,454.59,0\n'
    )
    statement = parse_activity_statement_csv(csv_text)
    assert len(statement.trades) == 1
    assert statement.forex_trades_skipped == 1
