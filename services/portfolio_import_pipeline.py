"""
Validation, normalization, and reconciliation layers around broker import.

Wraps the existing IBKR parser/importer without replacing it:

    Validate → Normalize → Existing importer → Fill gaps → Reconcile
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date
from typing import TYPE_CHECKING, Any

from services.ibkr_activity_parser import (
    IBKRActivityStatement,
    ImportIssue,
    ImportIssueLevel,
    build_monthly_deposits,
    expected_deposit_inflow_total,
    parse_statement_period,
    sum_deposit_inflows_base,
)
from utils.import_money import round_money, round_rate, round_shares

if TYPE_CHECKING:
    from services.portfolio_context import PortfolioContext

_MAX_SINGLE_DEPOSIT_EUR = 250_000.0
_MAX_TRADE_NOTIONAL_USD = 50_000_000.0
_MAX_MOM_JUMP_PCT = 75.0


def content_fingerprint(content: str | bytes) -> str:
    """Stable SHA-256 fingerprint for duplicate file detection."""
    payload = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(payload).hexdigest()


def normalize_statement(statement: IBKRActivityStatement) -> IBKRActivityStatement:
    """Round monetary fields to currency precision using Decimal."""
    statement.open_positions = [
        replace(
            position,
            shares=round_shares(position.shares),
            cost_price=round_money(position.cost_price),
            cost_basis=round_money(position.cost_basis),
        )
        for position in statement.open_positions
    ]
    statement.trades = [
        replace(
            trade,
            quantity=round_shares(trade.quantity),
            price_usd=round_money(trade.price_usd),
            commission_usd=round_money(trade.commission_usd),
        )
        for trade in statement.trades
    ]
    statement.dividends = [
        replace(
            dividend,
            per_share_usd=round_rate(dividend.per_share_usd),
            gross_usd=round_money(dividend.gross_usd),
        )
        for dividend in statement.dividends
    ]
    statement.cash_transfers = [
        replace(
            transfer,
            amount=round_money(transfer.amount),
        )
        for transfer in statement.cash_transfers
    ]
    if statement.nav_total is not None:
        statement.nav_total = round_money(statement.nav_total)
    if statement.deposits_fx_eur_per_usd is not None:
        statement.deposits_fx_eur_per_usd = round_rate(statement.deposits_fx_eur_per_usd)
    statement.fx_rates = {
        currency: round_rate(rate) for currency, rate in statement.fx_rates.items()
    }
    return statement


def validate_import_input(
    content: str | bytes,
    statement: IBKRActivityStatement,
) -> list[ImportIssue]:
    """Pre-import checks for mandatory metadata and malformed payloads."""
    issues: list[ImportIssue] = []

    if not str(content).strip():
        issues.append(
            ImportIssue(ImportIssueLevel.ERROR, "Uploaded file is empty.", section="Upload")
        )
        return issues

    if not statement.meta.account:
        issues.append(
            ImportIssue(
                ImportIssueLevel.WARNING,
                "Missing account number in Account Information.",
                section="Account Information",
            )
        )

    period = parse_statement_period(statement.meta.period or "")
    if statement.meta.period and period is None:
        issues.append(
            ImportIssue(
                ImportIssueLevel.WARNING,
                f"Could not parse statement period: {statement.meta.period!r}.",
                section="Statement",
            )
        )

    for trade in statement.trades:
        if trade.trade_date > date.today():
            issues.append(
                ImportIssue(
                    ImportIssueLevel.WARNING,
                    f"{trade.symbol}: trade date {trade.trade_date} is in the future.",
                    section="Trades",
                )
            )
            break

    return issues


def detect_in_statement_duplicates(statement: IBKRActivityStatement) -> list[ImportIssue]:
    """Flag duplicate event fingerprints inside one CSV export."""
    issues: list[ImportIssue] = []

    trade_keys: dict[tuple[object, ...], int] = {}
    for trade in statement.trades:
        key = (
            trade.symbol,
            trade.trade_date,
            trade.side,
            round_shares(trade.quantity),
            round_money(trade.price_usd),
            round_money(trade.commission_usd),
        )
        trade_keys[key] = trade_keys.get(key, 0) + 1
    dup_trades = sum(count - 1 for count in trade_keys.values() if count > 1)
    if dup_trades:
        issues.append(
            ImportIssue(
                ImportIssueLevel.WARNING,
                f"Found {dup_trades} duplicate trade row(s) in this file — only one will import.",
                section="Trades",
            )
        )

    dividend_keys: dict[tuple[object, ...], int] = {}
    for dividend in statement.dividends:
        key = (
            dividend.symbol,
            dividend.pay_date,
            round_rate(dividend.per_share_usd),
            round_money(dividend.gross_usd),
        )
        dividend_keys[key] = dividend_keys.get(key, 0) + 1
    dup_divs = sum(count - 1 for count in dividend_keys.values() if count > 1)
    if dup_divs:
        issues.append(
            ImportIssue(
                ImportIssueLevel.WARNING,
                f"Found {dup_divs} duplicate dividend row(s) in this file.",
                section="Dividends",
            )
        )

    return issues


def validate_extreme_values(statement: IBKRActivityStatement) -> list[ImportIssue]:
    """Flag unrealistic deposits, trade sizes, or NAV totals."""
    issues: list[ImportIssue] = []
    eur_per_usd = statement.deposits_fx_eur_per_usd or statement.fx_rates.get("EUR")

    for transfer in statement.cash_transfers:
        if transfer.amount <= 0:
            continue
        amount_eur = transfer.amount
        if transfer.currency == "USD" and eur_per_usd and eur_per_usd > 0:
            amount_eur = round_money(transfer.amount * eur_per_usd)
        if amount_eur > _MAX_SINGLE_DEPOSIT_EUR:
            issues.append(
                ImportIssue(
                    ImportIssueLevel.WARNING,
                    (
                        f"Unusually large deposit ({transfer.currency} {transfer.amount:,.2f} "
                        f"on {transfer.transfer_date}) — verify before importing."
                    ),
                    section="Deposits & Withdrawals",
                )
            )

    for trade in statement.trades:
        notional = round_money(trade.quantity * trade.price_usd)
        if notional > _MAX_TRADE_NOTIONAL_USD:
            issues.append(
                ImportIssue(
                    ImportIssueLevel.WARNING,
                    (
                        f"{trade.symbol}: trade notional ${notional:,.0f} on "
                        f"{trade.trade_date} looks unusually large."
                    ),
                    section="Trades",
                )
            )

    nav_eur = statement.nav_total
    if nav_eur is not None and eur_per_usd and eur_per_usd > 0:
        nav_eur = round_money(nav_eur * eur_per_usd)
    if nav_eur is not None and nav_eur > 100_000_000:
        issues.append(
            ImportIssue(
                ImportIssueLevel.WARNING,
                f"Statement NAV ({nav_eur:,.0f} EUR) is unusually high — verify totals.",
                section="Net Asset Value",
            )
        )

    return issues


def validate_stored_deposits_against_statement(
    deposits: list,
    statement: IBKRActivityStatement,
    *,
    merge_mode: bool = False,
) -> list[ImportIssue]:
    """Compare persisted monthly rows with freshly parsed IBKR deposit totals."""
    issues: list[ImportIssue] = []
    incoming = build_monthly_deposits(statement, include_zero_months=True)
    stored_by_key = {item.period_key: item for item in deposits}
    for item in incoming:
        if item.deposit_eur <= 0.01 and item.deposit_usd <= 0.01:
            continue
        period_key = f"{item.year:04d}-{item.month:02d}"
        stored = stored_by_key.get(period_key)
        if stored is None:
            issues.append(
                ImportIssue(
                    ImportIssueLevel.WARNING,
                    f"{item.label}: deposit month missing after import.",
                    section="Deposits & Withdrawals",
                )
            )
            continue
        eur_ok = (
            stored.deposit_eur + 0.05 >= item.deposit_eur
            if merge_mode
            else abs(stored.deposit_eur - item.deposit_eur) <= 0.05
        )
        usd_ok = (
            stored.deposit_usd + 0.05 >= item.deposit_usd
            if merge_mode
            else abs(stored.deposit_usd - item.deposit_usd) <= 0.05
        )
        if not eur_ok:
            issues.append(
                ImportIssue(
                    ImportIssueLevel.WARNING,
                    (
                        f"{item.label}: stored deposit €{stored.deposit_eur:,.2f} differs from "
                        f"parsed €{item.deposit_eur:,.2f}."
                    ),
                    section="Deposits & Withdrawals",
                )
            )
        if not usd_ok:
            issues.append(
                ImportIssue(
                    ImportIssueLevel.WARNING,
                    (
                        f"{item.label}: stored deposit ${stored.deposit_usd:,.2f} differs from "
                        f"parsed ${item.deposit_usd:,.2f}."
                    ),
                    section="Deposits & Withdrawals",
                )
            )
    return issues


def validate_stored_deposit_currency_pairs(deposits: list) -> list[ImportIssue]:
    """Ensure stored EUR and USD totals represent the same value month-by-month."""
    issues: list[ImportIssue] = []
    fx_samples: list[float] = []
    for item in deposits:
        if item.deposit_eur > 0.01 and item.deposit_usd > 0.01:
            fx_samples.append(item.deposit_eur / item.deposit_usd)
    if not fx_samples:
        return issues

    ref_fx = sorted(fx_samples)[len(fx_samples) // 2]
    tolerance = max(0.02, ref_fx * 0.01)
    for item in deposits:
        if item.deposit_eur <= 0.01 or item.deposit_usd <= 0.01:
            continue
        implied = item.deposit_eur / item.deposit_usd
        if abs(implied - ref_fx) > tolerance:
            issues.append(
                ImportIssue(
                    ImportIssueLevel.WARNING,
                    (
                        f"{item.label}: deposit €{item.deposit_eur:,.2f} and "
                        f"${item.deposit_usd:,.2f} are not FX-consistent "
                        f"(implied {implied:.4f}, portfolio median {ref_fx:.4f})."
                    ),
                    section="Deposits & Withdrawals",
                )
            )

    total_eur = round(sum(item.deposit_eur for item in deposits), 2)
    total_usd = round(sum(item.deposit_usd for item in deposits), 2)
    if total_usd > 0.01:
        implied_total_fx = total_eur / total_usd
        if abs(implied_total_fx - ref_fx) > tolerance:
            issues.append(
                ImportIssue(
                    ImportIssueLevel.WARNING,
                    (
                        f"Portfolio deposit totals (€{total_eur:,.2f}, ${total_usd:,.2f}) "
                        f"do not represent the same value at FX {ref_fx:.4f}."
                    ),
                    section="Deposits & Withdrawals",
                )
            )
    return issues


def _iter_calendar_months(start: date, end: date) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def run_post_import_checks(
    ctx: PortfolioContext,
    statement: IBKRActivityStatement,
    *,
    import_mode: Any = None,
) -> list[ImportIssue]:
    """Reconcile imported data against holdings and monthly evolution."""
    issues: list[ImportIssue] = []
    merge_mode = getattr(import_mode, "value", import_mode) == "merge"
    deposits = ctx.deposits.list_deposits()
    if not deposits:
        return issues

    period = parse_statement_period(statement.meta.period or "")
    if period:
        expected_months = set(_iter_calendar_months(period[0], period[1]))
        incoming = build_monthly_deposits(statement, include_zero_months=True)
        incoming_keys = {(item.year, item.month) for item in incoming}
        missing_in_statement = sorted(expected_months - incoming_keys)
        if missing_in_statement:
            issues.append(
                ImportIssue(
                    ImportIssueLevel.INFO,
                    (
                        f"Statement period spans {len(expected_months)} months; "
                        f"{len(missing_in_statement)} had no deposit or NAV rows in the export."
                    ),
                    section="Statement",
                )
            )

    stored_keys = {(item.period.year, item.period.month) for item in deposits}
    start = min(item.period for item in deposits)
    end = max(item.period for item in deposits)
    timeline_gaps = [key for key in _iter_calendar_months(start, end) if key not in stored_keys]
    if timeline_gaps:
        issues.append(
            ImportIssue(
                ImportIssueLevel.WARNING,
                (
                    f"Portfolio timeline still has {len(timeline_gaps)} calendar gap(s) "
                    "between earliest and latest deposit month."
                ),
                section="Deposits & Withdrawals",
            )
        )

    portfolio_rows = [item for item in deposits if item.portfolio_eur > 0]
    prev_value: float | None = None
    for item in sorted(portfolio_rows, key=lambda row: row.period):
        if prev_value is not None and prev_value > 0:
            jump_pct = abs((item.portfolio_eur - prev_value) / prev_value * 100)
            if jump_pct > _MAX_MOM_JUMP_PCT:
                issues.append(
                    ImportIssue(
                        ImportIssueLevel.WARNING,
                        (
                            f"{item.label}: portfolio value changed {jump_pct:.0f}% "
                            f"({prev_value:,.0f} → {item.portfolio_eur:,.0f} EUR) — review import."
                        ),
                        section="Deposits & Withdrawals",
                    )
                )
        prev_value = item.portfolio_eur

    open_symbols = {pos.symbol for pos in statement.open_positions}
    if open_symbols:
        holdings = {h.symbol: h for h in ctx.portfolio.list_holdings()}
        for symbol in sorted(open_symbols):
            holding = holdings.get(symbol)
            position = next(p for p in statement.open_positions if p.symbol == symbol)
            if holding is None:
                continue
            if abs(holding.shares - position.shares) > 0.05:
                issues.append(
                    ImportIssue(
                        ImportIssueLevel.WARNING,
                        (
                            f"{symbol}: stored holdings ({holding.shares:g} shares) differ "
                            f"from statement open position ({position.shares:g})."
                        ),
                        section="Open Positions",
                    )
                )

    parsed_inflows = round_money(sum_deposit_inflows_base(statement))
    expected_total = expected_deposit_inflow_total(statement)
    if parsed_inflows > 0 and expected_total is not None:
        expected_inflows = round_money(expected_total)
        tolerance = max(0.05, expected_inflows * 0.001)
        if expected_inflows > 0 and abs(parsed_inflows - expected_inflows) > tolerance:
            issues.append(
                ImportIssue(
                    ImportIssueLevel.WARNING,
                    (
                        f"Parsed deposit inflows ({parsed_inflows:,.2f}) differ from "
                        f"statement total ({expected_inflows:,.2f}) in account base currency."
                    ),
                    section="Deposits & Withdrawals",
                )
            )

    issues.extend(
        validate_stored_deposits_against_statement(
            deposits,
            statement,
            merge_mode=merge_mode,
        )
    )
    issues.extend(validate_stored_deposit_currency_pairs(deposits))

    return issues


def prepare_statement(content: str | bytes) -> tuple[IBKRActivityStatement, list[ImportIssue], str]:
    """
    Validate and normalize a statement before the existing importer runs.

    Returns ``(statement, issues, content_fingerprint)``.
    """
    from services.ibkr_activity_parser import parse_activity_statement_csv, validate_statement

    fingerprint = content_fingerprint(content)
    statement = normalize_statement(parse_activity_statement_csv(content))
    issues = validate_statement(statement)
    issues.extend(validate_import_input(content, statement))
    issues.extend(detect_in_statement_duplicates(statement))
    issues.extend(validate_extreme_values(statement))
    return statement, issues, fingerprint
