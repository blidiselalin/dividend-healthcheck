"""
Persist and refresh the monthly deposits timeline with computed portfolio values.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from services.ibkr_activity_parser import ImportIssue, ImportIssueLevel
from services.portfolio_monthly_valuation import (
    compute_monthly_portfolio_valuations,
    continuous_monthly_deposits,
    portfolio_eur_to_store,
)

if TYPE_CHECKING:
    from services.portfolio_context import PortfolioContext


def fill_missing_deposit_months(
    ctx: PortfolioContext,
    *,
    range_start: date | None = None,
    range_end: date | None = None,
) -> tuple[int, list[ImportIssue]]:
    """Insert zero-deposit rows for calendar gaps through the current month."""
    issues: list[ImportIssue] = []
    added = ctx.deposits.fill_calendar_gaps(
        range_start=range_start,
        range_end=range_end,
    )
    if added:
        months = ctx.deposits.list_deposits()
        start = min(item.period for item in months)
        end = max(item.period for item in months)
        issues.append(
            ImportIssue(
                ImportIssueLevel.INFO,
                (
                    f"Filled {added} missing calendar month(s) with zero deposits "
                    f"({start.strftime('%Y-%m')} → {end.strftime('%Y-%m')})."
                ),
                section="Deposits & Withdrawals",
            )
        )
    return added, issues


def backfill_monthly_portfolio_eur(
    ctx: PortfolioContext,
    *,
    db_path: Path | None = None,
) -> tuple[int, list[ImportIssue]]:
    """
    Write month-end portfolio € for every month from journal marks and library prices.

    Each month uses the latest available close on or before month-end; the current
    month uses the most recent library or live snapshot price per holding.
    """
    issues: list[ImportIssue] = []
    deposits = ctx.deposits.list_deposits()
    if not deposits:
        return 0, issues

    timeline = continuous_monthly_deposits(deposits, include_current_month=True)
    valuations = compute_monthly_portfolio_valuations(timeline, db_path=db_path)
    if not valuations and not any(item.portfolio_eur > 0 for item in deposits):
        return 0, issues

    updated = 0
    for deposit in timeline:
        valuation = valuations.get(deposit.period_key)
        stored = deposit.portfolio_eur if deposit.portfolio_eur > 0 else None
        target = portfolio_eur_to_store(stored=stored, valuation=valuation)
        if target is None:
            continue
        if abs(deposit.portfolio_eur - target) < 0.01:
            continue
        ctx.deposits.upsert_deposit(
            year=deposit.period.year,
            month=deposit.period.month,
            label=deposit.label,
            deposit_eur=deposit.deposit_eur,
            deposit_usd=deposit.deposit_usd,
            portfolio_eur=target,
        )
        updated += 1

    if updated:
        issues.append(
            ImportIssue(
                ImportIssueLevel.INFO,
                (
                    f"Updated portfolio € for {updated} month(s) from purchase journal "
                    "and latest available stock prices."
                ),
                section="Deposits & Withdrawals",
            )
        )
    return updated, issues


def sync_monthly_portfolio_timeline(
    ctx: PortfolioContext,
    *,
    db_path: Path | None = None,
    range_start: date | None = None,
    range_end: date | None = None,
) -> tuple[int, int, list[ImportIssue]]:
    """Ensure a continuous monthly timeline and computed portfolio € on every row."""
    issues: list[ImportIssue] = []
    months_filled, fill_issues = fill_missing_deposit_months(
        ctx,
        range_start=range_start,
        range_end=range_end,
    )
    issues.extend(fill_issues)
    portfolio_updates, portfolio_issues = backfill_monthly_portfolio_eur(ctx, db_path=db_path)
    issues.extend(portfolio_issues)
    return months_filled, portfolio_updates, issues
