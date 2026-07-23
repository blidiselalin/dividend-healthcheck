"""
Parse Interactive Brokers Activity Statement CSV (AS_Fv2 section format).
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_DIVIDEND_SYMBOL_RE = re.compile(r"^([A-Z][A-Z0-9.\-]{0,9})\s*\(")
_DIVIDEND_PER_SHARE_RE = re.compile(
    r"(?:Cash Dividend\s+)?USD\s+([0-9]+(?:\.[0-9]+)?)(?:\s+per Share|\s*\(|$)",
    re.IGNORECASE,
)
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class ImportIssueLevel(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class ImportIssue:
    level: ImportIssueLevel
    message: str
    section: str | None = None


@dataclass(frozen=True)
class IBKRStatementMeta:
    title: str | None = None
    period: str | None = None
    account: str | None = None
    base_currency: str | None = None
    when_generated: str | None = None


@dataclass(frozen=True)
class IBKROpenPosition:
    symbol: str
    shares: float
    cost_price: float
    cost_basis: float
    currency: str = "USD"


@dataclass(frozen=True)
class IBKRTrade:
    symbol: str
    trade_date: date
    quantity: float
    price_usd: float
    commission_usd: float
    side: str
    currency: str = "USD"


@dataclass(frozen=True)
class IBKRDividend:
    symbol: str
    pay_date: date
    per_share_usd: float
    gross_usd: float
    currency: str = "USD"
    description: str = ""


@dataclass(frozen=True)
class IBKRCashTransfer:
    """Incoming or outgoing cash from Deposits & Withdrawals."""

    transfer_date: date
    amount: float
    currency: str
    description: str = ""


@dataclass(frozen=True)
class IBKRMonthlyDeposit:
    """Aggregated deposit totals for one calendar month."""

    year: int
    month: int
    label: str
    deposit_usd: float
    deposit_eur: float
    portfolio_eur: float = 0.0


@dataclass
class IBKRActivityStatement:
    meta: IBKRStatementMeta = field(default_factory=IBKRStatementMeta)
    open_positions: list[IBKROpenPosition] = field(default_factory=list)
    trades: list[IBKRTrade] = field(default_factory=list)
    dividends: list[IBKRDividend] = field(default_factory=list)
    cash_transfers: list[IBKRCashTransfer] = field(default_factory=list)
    fx_rates: dict[str, float] = field(default_factory=dict)
    nav_total: float | None = None
    deposits_fx_eur_per_usd: float | None = None
    deposits_inflow_total_base: float | None = None
    issues: list[ImportIssue] = field(default_factory=list)
    forex_trades_skipped: int = 0


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip().strip('"')
    if not text or text in {"--", "-", "N/A"}:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _parse_trade_date(value: str) -> date | None:
    text = str(value).strip().strip('"')
    if not text:
        return None
    for fmt in ("%Y-%m-%d, %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_pay_date(value: str) -> date | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_activity_date(value: str | None) -> date | None:
    """Parse IBKR activity dates across common export formats."""
    if value is None:
        return None
    text = str(value).strip().strip('"')
    if not text:
        return None
    parsed = _parse_trade_date(text) or _parse_pay_date(text)
    if parsed is not None:
        return parsed
    for fmt in (
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d-%b-%Y",
        "%d-%b-%y",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    if " " in text:
        return _parse_activity_date(text.split(" ", 1)[0])
    return None


def _normalize_symbol(symbol: str) -> str | None:
    sym = symbol.strip().upper()
    if not sym or sym in {"TOTAL", "SUBTOTAL"}:
        return None
    if _SYMBOL_RE.match(sym):
        return sym
    return None


def _normalize_currency(value: str) -> str | None:
    currency = value.strip().upper()
    if _CURRENCY_RE.match(currency):
        return currency
    return None


def _header_map(row: list[str]) -> dict[str, int]:
    return {column.strip(): index for index, column in enumerate(row) if column.strip()}


def _cell(
    row: list[str],
    header_map: dict[str, int],
    *names: str,
    fallback_idx: int | None = None,
) -> str | None:
    for name in names:
        index = header_map.get(name)
        if index is not None and index < len(row):
            value = row[index].strip()
            if value:
                return value
    if fallback_idx is not None and fallback_idx < len(row):
        value = row[fallback_idx].strip()
        return value or None
    return None


def _is_internal_transfer(description: str) -> bool:
    lowered = description.strip().lower()
    return lowered.startswith("internal (transfer")


_DEPOSIT_TOTAL_LABELS = frozenset(
    {
        "Total",
        "Total in EUR",
        "Total in USD",
        "Total Deposits & Withdrawals in EUR",
        "Total Deposits & Withdrawals in USD",
    }
)


def _last_numeric_cell(row: list[str], *, start: int = 2) -> float | None:
    for cell in reversed(row[start:]):
        parsed = _parse_float(cell)
        if parsed is not None:
            return parsed
    return None


def _parse_deposits_withdrawals_data_row(
    row: list[str],
    header_map: dict[str, int],
) -> IBKRCashTransfer | None:
    """Parse one Deposits & Withdrawals data row across IBKR column layouts."""
    if len(row) < 5 or row[1].strip() != "Data":
        return None

    row_label = row[2].strip()
    if row_label in _DEPOSIT_TOTAL_LABELS or row_label.startswith("Total "):
        return None

    currency = _normalize_currency(
        _cell(row, header_map, "Currency", "CurrencyPrimary", fallback_idx=2)
    )
    date_idx = 3
    desc_idx = 4
    amount_idx = 5

    if currency is None and row_label == "Deposits & Withdrawals" and len(row) >= 7:
        currency = _normalize_currency(row[3])
        date_idx = 4
        desc_idx = 5
        amount_idx = 6
    elif currency is None:
        currency = _normalize_currency(row_label)

    if currency is None:
        return None

    date_text = _cell(
        row,
        header_map,
        "Settle Date",
        "SettleDate",
        "Date",
        "Report Date",
        "Date/Time",
        fallback_idx=date_idx,
    )
    transfer_date = _parse_activity_date(date_text)
    if transfer_date is None and date_idx < len(row):
        transfer_date = _parse_activity_date(row[date_idx])

    description = (_cell(row, header_map, "Description", fallback_idx=desc_idx) or "").strip()
    amount = _parse_float(_cell(row, header_map, "Amount", fallback_idx=amount_idx))
    if amount is None:
        amount = _last_numeric_cell(row, start=date_idx + 1)

    if transfer_date is None or amount is None or amount == 0:
        return None
    if _is_internal_transfer(description) or amount < 0:
        return None

    return IBKRCashTransfer(
        transfer_date=transfer_date,
        amount=amount,
        currency=currency,
        description=description,
    )


def _sum_deposit_inflows_base(statement: IBKRActivityStatement) -> float:
    """Sum positive deposit inflows converted to the account base currency."""
    base = (statement.meta.base_currency or "USD").strip().upper()
    total = 0.0
    eur_per_usd = _statement_eur_per_usd(statement)
    for transfer in statement.cash_transfers:
        if transfer.amount <= 0:
            continue
        if transfer.currency == base:
            total += transfer.amount
        elif base == "EUR" and transfer.currency == "USD" and eur_per_usd:
            total += transfer.amount * eur_per_usd
        elif base == "USD" and transfer.currency == "EUR" and eur_per_usd:
            total += transfer.amount / eur_per_usd
    return round(total, 2)


def _reconcile_deposit_parsing(statement: IBKRActivityStatement) -> None:
    if not statement.cash_transfers or statement.deposits_inflow_total_base is None:
        return
    base = (statement.meta.base_currency or "USD").strip().upper()
    parsed_total = _sum_deposit_inflows_base(statement)
    expected = statement.deposits_inflow_total_base
    if expected <= 0:
        return
    tolerance = max(0.05, expected * 0.001)
    if abs(parsed_total - expected) > tolerance:
        statement.issues.append(
            ImportIssue(
                ImportIssueLevel.WARNING,
                (
                    f"Parsed deposit inflows ({parsed_total:,.2f} {base}) do not match "
                    f"statement total ({expected:,.2f} {base}) — review Deposits & Withdrawals."
                ),
                section="Deposits & Withdrawals",
            )
        )


def _statement_eur_per_usd(statement: IBKRActivityStatement) -> float | None:
    if statement.deposits_fx_eur_per_usd and statement.deposits_fx_eur_per_usd > 0:
        return statement.deposits_fx_eur_per_usd
    base = (statement.meta.base_currency or "USD").strip().upper()
    if base == "USD":
        eur_rate = statement.fx_rates.get("EUR")
        if eur_rate and eur_rate > 0:
            return eur_rate
    return None


def _month_label(year: int, month: int) -> str:
    import calendar

    return f"{calendar.month_name[month]} {year}"


def parse_statement_period(period: str) -> tuple[date, date] | None:
    """Parse IBKR Period field, e.g. ``January 1, 2025 - December 31, 2025``."""
    text = str(period or "").strip().strip('"')
    if " - " not in text:
        return None
    start_text, end_text = text.split(" - ", 1)
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            start = datetime.strptime(start_text.strip(), fmt).date()
            end = datetime.strptime(end_text.strip(), fmt).date()
            return start, end
        except ValueError:
            continue
    return None


def statement_deposit_period(statement: IBKRActivityStatement) -> tuple[date, date] | None:
    """Statement month range for deposit sync — Period header or transfer date span."""
    parsed = parse_statement_period(statement.meta.period or "")
    if parsed:
        return parsed
    if not statement.cash_transfers:
        return None
    dates = [transfer.transfer_date for transfer in statement.cash_transfers]
    return min(dates), max(dates)


def _iter_calendar_months(start: date, end: date) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    year, month = start.year, start.month
    end_key = (end.year, end.month)
    while (year, month) <= end_key:
        months.append((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _nav_to_portfolio_eur(statement: IBKRActivityStatement) -> float:
    """Convert statement NAV total to EUR for the portfolio snapshot field."""
    if statement.nav_total is None or statement.nav_total <= 0:
        return 0.0
    base = (statement.meta.base_currency or "USD").strip().upper()
    if base == "EUR":
        return round(statement.nav_total, 2)
    if base == "USD":
        eur_rate = statement.fx_rates.get("EUR")
        if eur_rate and eur_rate > 0:
            return round(statement.nav_total * eur_rate, 2)
    return 0.0


def build_monthly_deposits(statement: IBKRActivityStatement) -> list[IBKRMonthlyDeposit]:
    """
    Aggregate Deposits & Withdrawals rows into monthly_deposits records.

    Counts positive cash inflows only (withdrawals are ignored for deposit totals).
    When the statement Period is present, emits every calendar month in that range
    (zero-deposit months included) and assigns NAV to the period's last month.
    """
    totals: dict[tuple[int, int], dict[str, float]] = defaultdict(lambda: {"USD": 0.0, "EUR": 0.0})
    for transfer in statement.cash_transfers:
        if transfer.amount <= 0:
            continue
        key = (transfer.transfer_date.year, transfer.transfer_date.month)
        bucket = totals[key]
        bucket[transfer.currency] = bucket.get(transfer.currency, 0.0) + transfer.amount

    period = parse_statement_period(statement.meta.period or "")
    if period:
        month_keys = set(_iter_calendar_months(period[0], period[1]))
        month_keys.update(totals)
        month_keys = sorted(month_keys)
    elif totals:
        month_keys = sorted(totals)
    else:
        return []

    nav_eur = _nav_to_portfolio_eur(statement)
    last_month = month_keys[-1]
    rows: list[IBKRMonthlyDeposit] = []
    eur_per_usd = _statement_eur_per_usd(statement)
    usd_per_eur = (1.0 / eur_per_usd) if eur_per_usd and eur_per_usd > 0 else None

    for year, month in month_keys:
        bucket = totals.get((year, month), {})
        deposit_usd = round(bucket.get("USD", 0.0), 2)
        deposit_eur = round(bucket.get("EUR", 0.0), 2)
        if deposit_eur == 0.0 and deposit_usd > 0 and eur_per_usd:
            deposit_eur = round(deposit_usd * eur_per_usd, 2)
        elif deposit_usd == 0.0 and deposit_eur > 0 and usd_per_eur:
            deposit_usd = round(deposit_eur * usd_per_eur, 2)
        portfolio_eur = nav_eur if (year, month) == last_month and nav_eur > 0 else 0.0
        rows.append(
            IBKRMonthlyDeposit(
                year=year,
                month=month,
                label=_month_label(year, month),
                deposit_usd=deposit_usd,
                deposit_eur=deposit_eur,
                portfolio_eur=portfolio_eur,
            )
        )
    return rows


def deposit_months_with_inflows(monthly: list[IBKRMonthlyDeposit]) -> int:
    """Count months that received a positive deposit inflow."""
    return sum(1 for item in monthly if item.deposit_eur > 0 or item.deposit_usd > 0)


def parse_activity_statement_csv(content: str | bytes) -> IBKRActivityStatement:  # noqa: C901
    """Parse IBKR Activity Statement CSV text into structured sections."""
    if isinstance(content, bytes):
        text = content.decode("utf-8-sig", errors="replace")
    else:
        text = content.lstrip("\ufeff")

    reader = csv.reader(io.StringIO(text))
    statement = IBKRActivityStatement()
    deposits_header_map: dict[str, int] = {}
    nav_header_map: dict[str, int] = {}
    deposits_subsection: str | None = None
    deposits_usd_gross: float | None = None

    for row in reader:
        if not row:
            continue
        section = row[0].strip()
        if section == "Statement" and len(row) >= 4 and row[1] == "Data":
            key = row[2].strip()
            value = row[3].strip()
            if key == "Title":
                statement.meta = IBKRStatementMeta(
                    title=value,
                    period=statement.meta.period,
                    account=statement.meta.account,
                    base_currency=statement.meta.base_currency,
                    when_generated=statement.meta.when_generated,
                )
            elif key == "Period":
                statement.meta = IBKRStatementMeta(
                    title=statement.meta.title,
                    period=value,
                    account=statement.meta.account,
                    base_currency=statement.meta.base_currency,
                    when_generated=statement.meta.when_generated,
                )
            elif key == "WhenGenerated":
                statement.meta = IBKRStatementMeta(
                    title=statement.meta.title,
                    period=statement.meta.period,
                    account=statement.meta.account,
                    base_currency=statement.meta.base_currency,
                    when_generated=value,
                )
        elif section == "Account Information" and len(row) >= 4 and row[1] == "Data":
            if row[2].strip() == "Account":
                statement.meta = IBKRStatementMeta(
                    title=statement.meta.title,
                    period=statement.meta.period,
                    account=row[3].strip(),
                    base_currency=statement.meta.base_currency,
                    when_generated=statement.meta.when_generated,
                )
            elif row[2].strip() == "Base Currency":
                statement.meta = IBKRStatementMeta(
                    title=statement.meta.title,
                    period=statement.meta.period,
                    account=statement.meta.account,
                    base_currency=row[3].strip(),
                    when_generated=statement.meta.when_generated,
                )
        elif section == "Open Positions" and len(row) >= 10 and row[1] == "Data":
            if row[2] != "Summary" or row[3] != "Stocks":
                continue
            currency = row[4].strip()
            if currency != "USD":
                continue
            symbol = _normalize_symbol(row[5])
            shares = _parse_float(row[6])
            cost_price = _parse_float(row[8])
            cost_basis = _parse_float(row[9])
            if symbol is None or shares is None or shares <= 0:
                continue
            if cost_price is None or cost_basis is None:
                statement.issues.append(
                    ImportIssue(
                        ImportIssueLevel.WARNING,
                        f"Open position {symbol} missing cost fields",
                        section="Open Positions",
                    )
                )
                continue
            statement.open_positions.append(
                IBKROpenPosition(
                    symbol=symbol,
                    shares=shares,
                    cost_price=cost_price,
                    cost_basis=cost_basis,
                    currency=currency,
                )
            )
        elif section == "Trades" and len(row) >= 12 and row[1] == "Data" and row[2] == "Order":
            if row[3] != "Stocks" or row[4] != "USD":
                if row[3] == "Forex":
                    statement.forex_trades_skipped += 1
                continue
            symbol = _normalize_symbol(row[5])
            trade_date = _parse_trade_date(row[6])
            quantity = _parse_float(row[7])
            price = _parse_float(row[8])
            commission = _parse_float(row[11])
            if symbol is None or trade_date is None or quantity is None or quantity == 0:
                continue
            if price is None or price <= 0:
                statement.issues.append(
                    ImportIssue(
                        ImportIssueLevel.WARNING,
                        f"Skipped trade for {symbol} — invalid price",
                        section="Trades",
                    )
                )
                continue
            side = "buy" if quantity > 0 else "sell"
            statement.trades.append(
                IBKRTrade(
                    symbol=symbol,
                    trade_date=trade_date,
                    quantity=abs(quantity),
                    price_usd=price,
                    commission_usd=abs(commission or 0.0),
                    side=side,
                    currency="USD",
                )
            )
        elif section == "Dividends" and len(row) >= 6 and row[1] == "Data":
            if row[2] != "USD":
                continue
            pay_date = _parse_pay_date(row[3])
            description = row[4].strip()
            gross = _parse_float(row[5])
            if pay_date is None or gross is None or gross <= 0:
                continue
            sym_match = _DIVIDEND_SYMBOL_RE.match(description)
            if not sym_match:
                statement.issues.append(
                    ImportIssue(
                        ImportIssueLevel.WARNING,
                        f"Could not parse dividend symbol: {description[:60]}",
                        section="Dividends",
                    )
                )
                continue
            symbol = sym_match.group(1)
            per_share_match = _DIVIDEND_PER_SHARE_RE.search(description)
            per_share = float(per_share_match.group(1)) if per_share_match else 0.0
            if per_share <= 0:
                per_share = round(gross, 6)
            statement.dividends.append(
                IBKRDividend(
                    symbol=symbol,
                    pay_date=pay_date,
                    per_share_usd=per_share,
                    gross_usd=gross,
                    currency="USD",
                    description=description,
                )
            )
        elif section == "Deposits & Withdrawals" and len(row) >= 4:
            if row[1] == "Header":
                deposits_header_map = _header_map(row)
                deposits_subsection = None
                continue
            if row[1] != "Data":
                continue

            row_label = row[2].strip()
            if row_label == "Total in EUR":
                usd_in_eur = _parse_float(_cell(row, deposits_header_map, "Amount", fallback_idx=5))
                if usd_in_eur and deposits_usd_gross and deposits_usd_gross > 0:
                    statement.deposits_fx_eur_per_usd = round(
                        usd_in_eur / deposits_usd_gross,
                        8,
                    )
                continue
            if row_label in _DEPOSIT_TOTAL_LABELS or row_label.startswith("Total "):
                total_amount = _parse_float(
                    _cell(row, deposits_header_map, "Amount", fallback_idx=5)
                )
                if total_amount is None:
                    total_amount = _last_numeric_cell(row, start=3)
                base = (statement.meta.base_currency or "USD").strip().upper()
                if row_label == "Total" and deposits_subsection == "USD" and total_amount:
                    deposits_usd_gross = total_amount
                if (
                    total_amount
                    and total_amount > 0
                    and row_label == "Total"
                    and deposits_subsection == base
                ):
                    statement.deposits_inflow_total_base = total_amount
                continue

            transfer = _parse_deposits_withdrawals_data_row(row, deposits_header_map)
            row_currency = _normalize_currency(
                _cell(row, deposits_header_map, "Currency", "CurrencyPrimary", fallback_idx=2)
            )
            if row_currency is None and row[2].strip() not in _DEPOSIT_TOTAL_LABELS:
                row_currency = _normalize_currency(row[2].strip())
            if row_currency is not None:
                deposits_subsection = row_currency
            if transfer is None:
                continue
            statement.cash_transfers.append(transfer)
        elif section == "Base Currency Exchange Rate" and len(row) >= 4 and row[1] == "Data":
            currency = _normalize_currency(row[2])
            rate = _parse_float(row[3])
            if currency and rate and rate > 0:
                statement.fx_rates[currency] = rate
        elif section == "Net Asset Value" and len(row) >= 4:
            if row[1] == "Header":
                nav_header_map = _header_map(row)
                continue
            if row[1] != "Data":
                continue
            asset_class = (_cell(row, nav_header_map, "Asset Class", fallback_idx=2) or "").strip()
            if asset_class.lower() != "total":
                continue
            current_total_idx = nav_header_map.get("Current Total")
            nav_value = None
            if current_total_idx is not None and current_total_idx < len(row):
                nav_value = _parse_float(row[current_total_idx])
            else:
                for cell in reversed(row[3:]):
                    parsed = _parse_float(cell)
                    if parsed is not None and parsed > 0:
                        nav_value = parsed
                        break
            if nav_value is not None:
                statement.nav_total = nav_value

    _reconcile_deposit_parsing(statement)
    return statement


def statement_has_importable_data(statement: IBKRActivityStatement) -> bool:
    """True when the statement contains holdings, activity, or cash flows to import."""
    return bool(
        statement.open_positions
        or statement.trades
        or statement.dividends
        or statement.cash_transfers
    )


def validate_statement(statement: IBKRActivityStatement) -> list[ImportIssue]:
    """Return validation issues; fatal errors block import."""
    issues = list(statement.issues)
    title_ok = statement.meta.title and "activity statement" in statement.meta.title.lower()
    if not title_ok and not statement_has_importable_data(statement):
        issues.append(
            ImportIssue(
                ImportIssueLevel.ERROR,
                "File does not look like an IBKR Activity Statement.",
            )
        )
    if not statement.open_positions:
        if statement_has_importable_data(statement):
            issues.append(
                ImportIssue(
                    ImportIssueLevel.WARNING,
                    "No open stock positions found — trades, dividends, and deposits will "
                    "still import.",
                )
            )
        else:
            issues.append(
                ImportIssue(
                    ImportIssueLevel.ERROR,
                    "No importable portfolio data found in statement.",
                )
            )
    symbols = [pos.symbol for pos in statement.open_positions]
    if symbols and len(symbols) != len(set(symbols)):
        issues.append(
            ImportIssue(
                ImportIssueLevel.ERROR,
                "Duplicate symbols in Open Positions section.",
            )
        )
    if not statement.trades:
        issues.append(
            ImportIssue(
                ImportIssueLevel.WARNING,
                "No stock trades in statement period — holdings will still import.",
            )
        )
    if not statement.dividends:
        issues.append(
            ImportIssue(
                ImportIssueLevel.WARNING,
                "No cash dividends in statement period.",
            )
        )
    if not statement.cash_transfers:
        issues.append(
            ImportIssue(
                ImportIssueLevel.WARNING,
                "No deposits or withdrawals in statement period.",
            )
        )
    return issues


def has_blocking_errors(issues: list[ImportIssue]) -> bool:
    return any(issue.level == ImportIssueLevel.ERROR for issue in issues)


def statement_symbol_scope(statement: IBKRActivityStatement) -> set[str]:
    """Symbols touched by open positions, trades, or dividends in the statement."""
    symbols = {pos.symbol for pos in statement.open_positions}
    symbols.update(trade.symbol for trade in statement.trades)
    symbols.update(dividend.symbol for dividend in statement.dividends)
    return symbols
