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
