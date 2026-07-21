"""
Parse Interactive Brokers Activity Statement CSV (AS_Fv2 section format).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_DIVIDEND_SYMBOL_RE = re.compile(r"^([A-Z][A-Z0-9.\-]{0,9})\s*\(")
_DIVIDEND_PER_SHARE_RE = re.compile(
    r"(?:Cash Dividend\s+)?USD\s+([0-9]+(?:\.[0-9]+)?)(?:\s+per Share|\s*\(|$)",
    re.IGNORECASE,
)


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


@dataclass
class IBKRActivityStatement:
    meta: IBKRStatementMeta = field(default_factory=IBKRStatementMeta)
    open_positions: list[IBKROpenPosition] = field(default_factory=list)
    trades: list[IBKRTrade] = field(default_factory=list)
    dividends: list[IBKRDividend] = field(default_factory=list)
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


def _normalize_symbol(symbol: str) -> str | None:
    sym = symbol.strip().upper()
    if not sym or sym in {"TOTAL", "SUBTOTAL"}:
        return None
    if _SYMBOL_RE.match(sym):
        return sym
    return None


def parse_activity_statement_csv(content: str | bytes) -> IBKRActivityStatement:  # noqa: C901
    """Parse IBKR Activity Statement CSV text into structured sections."""
    if isinstance(content, bytes):
        text = content.decode("utf-8-sig", errors="replace")
    else:
        text = content.lstrip("\ufeff")

    reader = csv.reader(io.StringIO(text))
    statement = IBKRActivityStatement()

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

    return statement


def validate_statement(statement: IBKRActivityStatement) -> list[ImportIssue]:
    """Return validation issues; fatal errors block import."""
    issues = list(statement.issues)
    title_ok = statement.meta.title and "activity statement" in statement.meta.title.lower()
    if not title_ok and not statement.open_positions and not statement.trades:
        issues.append(
            ImportIssue(
                ImportIssueLevel.ERROR,
                "File does not look like an IBKR Activity Statement.",
            )
        )
    if not statement.open_positions:
        issues.append(
            ImportIssue(
                ImportIssueLevel.ERROR,
                "No open stock positions found (Open Positions → Summary → Stocks → USD).",
            )
        )
    symbols = [pos.symbol for pos in statement.open_positions]
    if len(symbols) != len(set(symbols)):
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
    return issues


def has_blocking_errors(issues: list[ImportIssue]) -> bool:
    return any(issue.level == ImportIssueLevel.ERROR for issue in issues)
