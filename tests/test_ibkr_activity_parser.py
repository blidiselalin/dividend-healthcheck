"""Tests for IBKR Activity Statement CSV parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.ibkr_activity_parser import (
    ImportIssueLevel,
    build_monthly_deposits,
    deposit_months_with_inflows,
    has_blocking_errors,
    parse_activity_statement_csv,
    parse_statement_period,
    statement_deposit_period,
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
    assert len(statement.cash_transfers) == 2
    assert statement.nav_total == pytest.approx(3500.0)
    assert statement.fx_rates["EUR"] == pytest.approx(0.92)
    aapl_div = next(d for d in statement.dividends if d.symbol == "AAPL")
    assert aapl_div.per_share_usd == 0.25
    assert aapl_div.gross_usd == 2.50


def test_statement_symbol_scope_includes_trades_and_dividends(sample_csv: str) -> None:
    from services.ibkr_activity_parser import statement_symbol_scope

    statement = parse_activity_statement_csv(sample_csv)
    assert statement_symbol_scope(statement) == {"AAPL", "MSFT"}


def test_build_monthly_deposits_aggregates_inflows(sample_csv: str) -> None:
    statement = parse_activity_statement_csv(sample_csv)
    monthly = build_monthly_deposits(statement)
    assert len(monthly) == 12
    assert deposit_months_with_inflows(monthly) == 2
    feb = next(item for item in monthly if item.month == 2)
    mar = next(item for item in monthly if item.month == 3)
    dec = next(item for item in monthly if item.month == 12)
    assert feb.deposit_usd == 2000.0
    assert feb.deposit_eur == pytest.approx(1840.0)
    assert mar.deposit_usd == 1500.0
    assert mar.deposit_eur == pytest.approx(1380.0)
    assert dec.portfolio_eur == pytest.approx(3220.0)
    assert mar.portfolio_eur == 0.0


def test_validate_sample_has_no_blocking_errors(sample_csv: str) -> None:
    statement = parse_activity_statement_csv(sample_csv)
    issues = validate_statement(statement)
    assert not has_blocking_errors(issues)


def test_validate_rejects_non_ibkr_file() -> None:
    statement = parse_activity_statement_csv("foo,bar\n")
    issues = validate_statement(statement)
    assert has_blocking_errors(issues)
    assert any(issue.level == ImportIssueLevel.ERROR for issue in issues)


def test_validate_allows_import_without_open_positions() -> None:
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        'Trades,Data,Order,Stocks,USD,AAPL,"2025-02-13, 09:30:00",10,150,1500,USD,-1.25\n'
        'Dividends,Data,USD,2025-03-15,"AAPL(US0378331005) Cash Dividend USD 0.25 per Share",2.50\n'
        "Deposits & Withdrawals,Data,USD,2025-02-01,Electronic Fund Transfer,1000,USD\n"
    )
    statement = parse_activity_statement_csv(csv_text)
    issues = validate_statement(statement)
    assert not has_blocking_errors(issues)
    assert any(
        issue.level == ImportIssueLevel.WARNING and "No open stock positions" in issue.message
        for issue in issues
    )


def test_validate_rejects_statement_with_no_importable_data() -> None:
    csv_text = "Statement,Data,Title,Activity Statement\n"
    statement = parse_activity_statement_csv(csv_text)
    issues = validate_statement(statement)
    assert has_blocking_errors(issues)
    assert any("No importable portfolio data" in issue.message for issue in issues)


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


def test_parse_eur_base_deposits_with_header_and_fx() -> None:
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        'Statement,Data,Period,"February 1, 2025 - February 28, 2025"\n'
        "Account Information,Data,Base Currency,EUR\n"
        "Net Asset Value,Header,Asset Class,Prior Total,Current Long,"
        "Current Short,Current Total,Change\n"
        "Net Asset Value,Data,Total,64658.07,99084.96,0,99084.96,34426.88\n"
        "Deposits & Withdrawals,Header,Currency,Settle Date,Description,Amount\n"
        "Deposits & Withdrawals,Data,EUR,2025-02-13,Electronic Fund Transfer,2500\n"
        "Deposits & Withdrawals,Data,EUR,2025-02-17,Electronic Fund Transfer,5300\n"
        "Deposits & Withdrawals,Data,Total,,,7800\n"
        "Deposits & Withdrawals,Data,USD,2025-02-03,Internal (Transfer to U15587745),4.21\n"
        "Deposits & Withdrawals,Data,Total,,,4.21\n"
        "Deposits & Withdrawals,Data,Total in EUR,,,4.01\n"
    )
    statement = parse_activity_statement_csv(csv_text)
    assert statement.meta.base_currency == "EUR"
    assert statement.nav_total == pytest.approx(99084.96)
    assert len(statement.cash_transfers) == 2
    assert statement.deposits_fx_eur_per_usd == pytest.approx(4.01 / 4.21)

    monthly = build_monthly_deposits(statement)
    assert len(monthly) == 1
    feb = monthly[0]
    assert feb.deposit_eur == 7800.0
    assert feb.deposit_usd == pytest.approx(7800.0 * (4.21 / 4.01))
    assert feb.portfolio_eur == pytest.approx(99084.96)


def test_parse_statement_period() -> None:
    parsed = parse_statement_period("January 1, 2025 - December 31, 2025")
    assert parsed is not None
    assert parsed[0].isoformat() == "2025-01-01"
    assert parsed[1].isoformat() == "2025-12-31"


def test_parse_deposits_with_asset_category_column() -> None:
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        "Deposits & Withdrawals,Header,Asset Category,Currency,Settle Date,"
        "Description,Amount\n"
        "Deposits & Withdrawals,Data,Deposits & Withdrawals,EUR,2025-03-05,"
        "Electronic Fund Transfer,1800\n"
    )
    statement = parse_activity_statement_csv(csv_text)
    assert len(statement.cash_transfers) == 1
    assert statement.cash_transfers[0].currency == "EUR"
    assert statement.cash_transfers[0].amount == 1800.0


def test_parse_all_2025_deposit_fixture() -> None:
    fixture = Path(__file__).resolve().parent / "fixtures" / "ibkr_deposits_2025.csv"
    statement = parse_activity_statement_csv(fixture.read_text(encoding="utf-8"))
    assert len(statement.cash_transfers) == 20
    assert statement.deposits_inflow_total_base == pytest.approx(34460.79)
    assert not any(
        issue.level == ImportIssueLevel.WARNING and "do not match" in issue.message
        for issue in statement.issues
    )
    monthly = build_monthly_deposits(statement)
    assert len(monthly) == 12
    assert deposit_months_with_inflows(monthly) == 11
    assert sum(item.deposit_eur for item in monthly) == pytest.approx(34460.79)
    assert next(item for item in monthly if item.month == 11).deposit_eur == 0.0


def test_parse_deposits_us_date_format() -> None:
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        "Account Information,Data,Base Currency,USD\n"
        "Deposits & Withdrawals,Header,Currency,Date,Description,Amount\n"
        "Deposits & Withdrawals,Data,USD,01/15/2025,Electronic Fund Transfer,500\n"
        "Deposits & Withdrawals,Data,Total,,,500\n"
    )
    statement = parse_activity_statement_csv(csv_text)
    assert len(statement.cash_transfers) == 1
    assert statement.cash_transfers[0].transfer_date.isoformat() == "2025-01-15"
    assert statement.deposits_inflow_total_base == pytest.approx(500.0)


def test_dual_currency_deposits_in_same_month_are_combined() -> None:
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        'Statement,Data,Period,"January 1, 2026 - July 31, 2026"\n'
        "Account Information,Data,Base Currency,EUR\n"
        "Deposits & Withdrawals,Header,Currency,Settle Date,Description,Amount\n"
        "Deposits & Withdrawals,Data,EUR,2026-05-11,Electronic Fund Transfer,700.07\n"
        "Deposits & Withdrawals,Data,USD,2026-05-06,Electronic Fund Transfer,4000\n"
        "Deposits & Withdrawals,Data,Total,,,700.07\n"
        "Deposits & Withdrawals,Data,USD,2026-01-29,Electronic Fund Transfer,100\n"
        "Deposits & Withdrawals,Data,Total,,,4100\n"
        "Deposits & Withdrawals,Data,Total in EUR,,,3520.07\n"
        "Deposits & Withdrawals,Data,Total Deposits & Withdrawals in EUR,,,4220.14\n"
    )
    statement = parse_activity_statement_csv(csv_text)
    monthly = build_monthly_deposits(statement)
    may = next(item for item in monthly if item.month == 5)
    assert may.deposit_usd == 4000.0
    fx = statement.deposits_fx_eur_per_usd
    assert fx is not None
    assert may.deposit_eur == pytest.approx(700.07 + 4000 * fx, rel=1e-4)


def test_statement_deposit_period_falls_back_to_transfer_dates() -> None:
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        "Account Information,Data,Base Currency,EUR\n"
        "Deposits & Withdrawals,Header,Currency,Settle Date,Description,Amount\n"
        "Deposits & Withdrawals,Data,EUR,2025-02-01,Electronic Fund Transfer,1000\n"
        "Deposits & Withdrawals,Data,EUR,2025-04-05,Electronic Fund Transfer,250\n"
        "Deposits & Withdrawals,Data,Total,,,1250\n"
    )
    statement = parse_activity_statement_csv(csv_text)
    period = statement_deposit_period(statement)
    assert period is not None
    assert period[0].isoformat() == "2025-02-01"
    assert period[1].isoformat() == "2025-04-05"


def test_deposit_outside_statement_period_is_included() -> None:
    csv_text = (
        "Statement,Data,Title,Activity Statement\n"
        'Statement,Data,Period,"January 1, 2025 - March 31, 2025"\n'
        "Account Information,Data,Base Currency,EUR\n"
        "Deposits & Withdrawals,Header,Currency,Settle Date,Description,Amount\n"
        "Deposits & Withdrawals,Data,EUR,2025-02-01,Electronic Fund Transfer,1000\n"
        "Deposits & Withdrawals,Data,EUR,2025-04-05,Electronic Fund Transfer,250\n"
        "Deposits & Withdrawals,Data,Total,,,1250\n"
    )
    statement = parse_activity_statement_csv(csv_text)
    monthly = build_monthly_deposits(statement)
    active = {(item.year, item.month) for item in monthly if item.deposit_eur > 0}
    assert active == {(2025, 2), (2025, 4)}
