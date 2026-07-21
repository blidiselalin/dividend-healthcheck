"""
Flag portfolio holdings: dividend timing (separate list) vs negative risk signals.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

import pandas as pd

from services.portfolio_details_service import PortfolioDetailRow
from services.portfolio_dividend_calendar import build_portfolio_dividend_calendar
from services.portfolio_zone_overview import zone_to_category

if TYPE_CHECKING:
    from services.news_service import NewsSummary
    from services.portfolio_analysis_preload import PortfolioAnalysisPreload

EX_DATE_SOON_DAYS = 21
OVERWEIGHT_WEIGHT_PCT = 10.0
PROFIT_WARN_PCT = -12.0
PROFIT_ALERT_PCT = -20.0
DECLINE_180_WARN_PCT = -18.0
DECLINE_365_WARN_PCT = -25.0
TARGET_DOWNSIDE_WARN_PCT = -15.0

# Risk watchlist: only material, high-severity issues (keeps counts actionable).
RISK_MIN_SCORE = 42
RISK_HIGH_SCORE = 52

# Buy opportunities: yield-zone value + supportive fundamentals.
OPPORTUNITY_MIN_SCORE = 30
OPPORTUNITY_HIGH_SCORE = 48
OPPORTUNITY_MIN_GAP_TO_FAIR_PCT = 6.0

DIVIDEND_CATEGORY = "Dividend"
OPPORTUNITY_CATEGORY = "Opportunity"
NEGATIVE_CATEGORIES = frozenset({"Exposure", "Estimates", "News"})


@dataclass(frozen=True)
class AttentionItem:
    symbol: str
    company: str
    severity: str  # high | medium | low (risk / buy lists only)
    score: int
    categories: tuple[str, ...]
    reasons: tuple[str, ...]
    portfolio_weight_pct: float | None = None
    profit_pct: float | None = None
    timing: str | None = None  # dividend list: upcoming ex-date, paid, etc.
    ex_date: date | None = None
    pay_date: date | None = None


@dataclass
class AttentionSummary:
    """Risk (high severity only), buy opportunities, and dividend timing — separate lists."""

    risk_items: list[AttentionItem] = field(default_factory=list)
    opportunity_items: list[AttentionItem] = field(default_factory=list)
    dividend_items: list[AttentionItem] = field(default_factory=list)
    reference_date: date = field(default_factory=date.today)

    @property
    def items(self) -> list[AttentionItem]:
        """Backward compatibility: attention watchlist = high-risk only."""
        return self.risk_items

    @property
    def total(self) -> int:
        return len(self.risk_items)

    @property
    def opportunity_total(self) -> int:
        return len(self.opportunity_items)

    @property
    def dividend_total(self) -> int:
        return len(self.dividend_items)

    @property
    def high_count(self) -> int:
        """High-priority buy opportunities (not risk severity)."""
        return sum(1 for item in self.opportunity_items if item.severity == "high")

    @property
    def dividend_upcoming_ex_count(self) -> int:
        from services.dividend_timing import TIMING_LABELS, UPCOMING_EX

        label = TIMING_LABELS[UPCOMING_EX]
        return sum(1 for item in self.dividend_items if item.timing == label)

    @property
    def by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.risk_items:
            for category in item.categories:
                counts[category] = counts.get(category, 0) + 1
        return counts


def split_legacy_attention_items(
    items: Sequence[AttentionItem],
    reference_date: date | None = None,
) -> AttentionSummary:
    """Convert pre-split cached items into risk + dividend lists."""
    risk_items: list[AttentionItem] = []
    dividend_items: list[AttentionItem] = []
    ref = reference_date or date.today()

    for item in items:
        if DIVIDEND_CATEGORY in item.categories and len(item.categories) == 1:
            dividend_items.append(item)
            continue
        if DIVIDEND_CATEGORY in item.categories:
            div_reasons = tuple(
                r for r in item.reasons if "dividend" in r.lower() or "ex-div" in r.lower()
            )
            risk_reasons = tuple(r for r in item.reasons if r not in div_reasons)
            risk_cats = tuple(c for c in item.categories if c != DIVIDEND_CATEGORY)
            if div_reasons:
                dividend_items.append(
                    AttentionItem(
                        symbol=item.symbol,
                        company=item.company,
                        severity=item.severity,
                        score=item.score,
                        categories=(DIVIDEND_CATEGORY,),
                        reasons=div_reasons,
                        portfolio_weight_pct=item.portfolio_weight_pct,
                        profit_pct=item.profit_pct,
                    )
                )
            if risk_cats and risk_reasons:
                risk_items.append(
                    AttentionItem(
                        symbol=item.symbol,
                        company=item.company,
                        severity=item.severity,
                        score=item.score,
                        categories=risk_cats,
                        reasons=risk_reasons,
                        portfolio_weight_pct=item.portfolio_weight_pct,
                        profit_pct=item.profit_pct,
                    )
                )
            continue
        risk_items.append(item)

    return AttentionSummary(
        risk_items=risk_items,
        dividend_items=dividend_items,
        reference_date=ref,
    )


def normalize_attention_summary(summary: Any) -> AttentionSummary | None:
    """Support dict cache, new objects, and legacy session-state summaries."""
    if summary is None:
        return None
    if isinstance(summary, dict):
        from services.portfolio_risk_monitor_service import PortfolioRiskMonitorService

        return PortfolioRiskMonitorService.summary_from_store(summary)

    if isinstance(summary, AttentionSummary):
        fields = getattr(summary, "__dict__", {})
        if "risk_items" in fields:
            return summary
        legacy_items = fields.get("items")
        if legacy_items is not None:
            return split_legacy_attention_items(
                legacy_items,
                fields.get("reference_date"),
            )
        return AttentionSummary(reference_date=fields.get("reference_date", date.today()))

    legacy_items = getattr(summary, "items", None)
    if legacy_items is not None:
        return split_legacy_attention_items(
            legacy_items,
            getattr(summary, "reference_date", None),
        )
    return None


class PortfolioAttentionService:
    """Build ranked dividend and risk attention lists from portfolio rows."""

    def build_summary(
        self,
        rows: Sequence[PortfolioDetailRow],
        preload: PortfolioAnalysisPreload,
        *,
        reference_date: date | None = None,
        news_by_symbol: dict[str, NewsSummary] | None = None,
    ) -> AttentionSummary:
        today = reference_date or date.today()
        from services.portfolio_context import create_portfolio_context

        holdings = create_portfolio_context().portfolio.list_holdings()
        row_dates = {row.ticker: (row.ex_dividend_date, row.dividend_pay_date) for row in rows}
        calendar = build_portfolio_dividend_calendar(
            holdings,
            vector_docs=preload.vector_docs,
            stock_data=preload.stock_data,
            row_dates=row_dates,
            reference_date=today,
        )

        current_payers = {item.symbol for item in calendar.current_month.holdings}
        next_payers = {item.symbol for item in calendar.next_month.holdings}
        scheduled_now = {
            item.symbol
            for item in calendar.current_month.holdings
            if item.status in ("scheduled", "projected")
        }

        risk_scored: list[AttentionItem] = []
        opportunity_scored: list[AttentionItem] = []
        dividend_scored: list[AttentionItem] = []
        for row in rows:
            dividend_flags = self._evaluate_dividend_attention(
                row,
                today=today,
                current_payers=current_payers,
                next_payers=next_payers,
                scheduled_now=scheduled_now,
            )
            risk_flags = self._evaluate_risk_attention(
                row,
                preload=preload,
                news=news_by_symbol.get(row.ticker) if news_by_symbol else None,
            )
            opportunity_flags = self._evaluate_buy_opportunity(row, preload=preload)
            if dividend_flags:
                timing, reasons = dividend_flags
                dividend_scored.append(
                    AttentionItem(
                        symbol=row.ticker,
                        company=row.company,
                        severity="low",
                        score=0,
                        categories=(DIVIDEND_CATEGORY,),
                        reasons=tuple(reasons),
                        portfolio_weight_pct=row.weight_pct,
                        profit_pct=row.profit_pct,
                        timing=timing,
                        ex_date=row.ex_dividend_date,
                        pay_date=row.dividend_pay_date,
                    )
                )
            if risk_flags:
                score, severity, categories, reasons = risk_flags
                if severity == "high":
                    risk_scored.append(
                        AttentionItem(
                            symbol=row.ticker,
                            company=row.company,
                            severity=severity,
                            score=score,
                            categories=tuple(sorted(categories)),
                            reasons=tuple(reasons),
                            portfolio_weight_pct=row.weight_pct,
                            profit_pct=row.profit_pct,
                        )
                    )
            if opportunity_flags:
                score, severity, categories, reasons = opportunity_flags
                opportunity_scored.append(
                    AttentionItem(
                        symbol=row.ticker,
                        company=row.company,
                        severity=severity,
                        score=score,
                        categories=tuple(sorted(categories)),
                        reasons=tuple(reasons),
                        portfolio_weight_pct=row.weight_pct,
                        profit_pct=row.profit_pct,
                    )
                )

        risk_scored.sort(key=lambda item: (-item.score, item.symbol))
        opportunity_scored.sort(key=lambda item: (-item.score, item.symbol))
        dividend_scored.sort(key=lambda item: (-item.score, item.symbol))
        return AttentionSummary(
            risk_items=risk_scored,
            opportunity_items=opportunity_scored,
            dividend_items=dividend_scored,
            reference_date=today,
        )

    def _evaluate_dividend_attention(  # noqa: C901
        self,
        row: PortfolioDetailRow,
        *,
        today: date,
        current_payers: set[str],
        next_payers: set[str],
        scheduled_now: set[str],
    ) -> tuple[str, list[str]] | None:
        from services.dividend_timing import classify_dividend_timing

        reasons: list[str] = []
        timing = classify_dividend_timing(
            today=today,
            ex_date=row.ex_dividend_date,
            pay_date=row.dividend_pay_date,
        )

        if row.ex_dividend_date:
            days_to_ex = (row.ex_dividend_date - today).days
            if days_to_ex > 0:
                reasons.append(f"Ex-dividend in {days_to_ex} day(s) ({row.ex_dividend_date:%d %b})")
            elif days_to_ex == 0:
                reasons.append(f"Ex-dividend today ({row.ex_dividend_date:%d %b})")
            elif row.dividend_pay_date and row.dividend_pay_date > today:
                reasons.append(
                    f"Ex-date passed ({row.ex_dividend_date:%d %b}); "
                    f"payment expected {row.dividend_pay_date:%d %b}"
                )

        if (
            row.dividend_pay_date
            and row.dividend_pay_date > today
            and not any("payment" in r.lower() or "pay" in r.lower() for r in reasons)
        ):
            reasons.append(f"Payment date {row.dividend_pay_date:%d %b}")

        if row.ticker in scheduled_now:
            reasons.append("Payment scheduled or projected this month")
        elif row.ticker in current_payers and row.ticker not in scheduled_now:
            reasons.append("Dividend cash expected this month")
        elif row.ticker in next_payers:
            reasons.append("Dividend expected next month")

        from services.dividend_timing import PAID, TIMING_LABELS

        if timing == TIMING_LABELS[PAID]:
            return None

        if not reasons:
            return None

        return timing, reasons[:5]

    def _evaluate_risk_attention(  # noqa: C901
        self,
        row: PortfolioDetailRow,
        *,
        preload: PortfolioAnalysisPreload,
        news: NewsSummary | None,
    ) -> tuple[int, str, set[str], list[str]] | None:
        """Flag only material, compounded risk — surfaced on watchlist if severity is high."""
        score = 0
        categories: set[str] = set()
        reasons: list[str] = []

        channel = preload.yield_channels.get(row.ticker)
        zone_category = zone_to_category(channel.zone) if channel else "unknown"
        loss_pct = row.profit_pct

        if channel and zone_category == "red":
            if loss_pct is not None and loss_pct <= PROFIT_WARN_PCT:
                score += 22
                categories.add("Exposure")
                reasons.append(
                    f"Expensive yield zone ({channel.zone}) with {loss_pct:+.1f}% unrealized loss"
                )
            elif loss_pct is not None and loss_pct < -5:
                score += 14
                categories.add("Exposure")
                reasons.append(
                    f"Expensive yield zone ({channel.zone}) while underwater ({loss_pct:+.1f}%)"
                )

        if loss_pct is not None:
            if loss_pct <= PROFIT_ALERT_PCT:
                score += 36
                categories.add("Exposure")
                reasons.append(f"Severe unrealized loss ({loss_pct:+.1f}%)")
            elif loss_pct <= PROFIT_WARN_PCT:
                score += 20
                categories.add("Exposure")
                reasons.append(f"Deep unrealized loss ({loss_pct:+.1f}%)")

        if (
            row.change_365d_pct is not None
            and row.change_365d_pct <= DECLINE_365_WARN_PCT
            and loss_pct is not None
            and loss_pct < 0
        ):
            score += 16
            categories.add("Exposure")
            reasons.append(
                f"Price down {abs(row.change_365d_pct):.1f}% over 12 months "
                f"with {loss_pct:+.1f}% position loss"
            )
        elif (
            row.change_180d_pct is not None
            and row.change_180d_pct <= DECLINE_180_WARN_PCT
            and loss_pct is not None
            and loss_pct <= PROFIT_WARN_PCT
        ):
            score += 12
            categories.add("Exposure")
            reasons.append(
                f"Price down {abs(row.change_180d_pct):.1f}% over 6 months "
                f"with {loss_pct:+.1f}% loss"
            )

        rating = (row.analyst_rating or "").upper()
        if rating in {"AVOID", "SELL", "STRONG SELL", "UNDERPERFORM"}:
            score += 34
            categories.add("Estimates")
            reasons.append(f"Analyst view: {row.analyst_rating}")

        stock = preload.stock_data.get(row.ticker)
        if (
            stock
            and stock.target_upside_pct is not None
            and stock.target_upside_pct <= TARGET_DOWNSIDE_WARN_PCT
            and loss_pct is not None
            and loss_pct < 0
        ):
            score += 18
            categories.add("Estimates")
            reasons.append(
                f"Consensus target implies {stock.target_upside_pct:+.1f}% downside while at a loss"
            )

        if (
            row.weight_pct is not None
            and row.weight_pct >= OVERWEIGHT_WEIGHT_PCT
            and len(categories) >= 2
        ):
            score += 10
            categories.add("Exposure")
            reasons.append(f"Concentrated position ({row.weight_pct:.1f}% of portfolio)")

        if news and score >= 25:
            if news.overall_sentiment in ("bearish",) or news.sentiment_score <= -0.4:
                score += 18
                categories.add("News")
                reasons.append(f"Recent news sentiment: {news.overall_sentiment}")
            elif news.negative_count >= 3 and news.negative_count > news.positive_count:
                score += 12
                categories.add("News")
                reasons.append(
                    f"Headline skew negative ({news.negative_count} vs {news.positive_count})"
                )

        if score < RISK_MIN_SCORE or not categories:
            return None
        if len(categories) < 2 and score < RISK_HIGH_SCORE:
            return None

        severity = "high" if score >= RISK_HIGH_SCORE else "medium"
        return score, severity, categories, reasons[:5]

    def _evaluate_buy_opportunity(  # noqa: C901
        self,
        row: PortfolioDetailRow,
        *,
        preload: PortfolioAnalysisPreload,
    ) -> tuple[int, str, set[str], list[str]] | None:
        """Rank holdings that fit a disciplined buy thesis (yield zone + quality signals)."""
        channel = preload.yield_channels.get(row.ticker)
        if not channel:
            return None

        zone_category = zone_to_category(channel.zone)
        if zone_category == "red":
            return None

        rating = (row.analyst_rating or "").upper()
        if rating in {"AVOID", "SELL", "STRONG SELL", "UNDERPERFORM"}:
            return None
        if row.profit_pct is not None and row.profit_pct <= PROFIT_ALERT_PCT:
            return None

        score = 0
        categories: set[str] = set()
        reasons: list[str] = []

        if channel.zone == "Deep Value":
            score += 38
            categories.add(OPPORTUNITY_CATEGORY)
            reasons.append("Deep value yield zone — historically high dividend yield")
        elif zone_category == "green":
            score += 30
            categories.add(OPPORTUNITY_CATEGORY)
            reasons.append(f"Buy-zone yield ({channel.zone}) vs long-term history")

        gap_fair_pct: float | None = None
        if channel.current_price and channel.fair_value_price:
            gap_fair_pct = ((channel.fair_value_price / channel.current_price) - 1) * 100
            if gap_fair_pct >= OPPORTUNITY_MIN_GAP_TO_FAIR_PCT:
                score += 14
                categories.add(OPPORTUNITY_CATEGORY)
                reasons.append(f"Price {gap_fair_pct:.0f}% below fair-value yield level")
            elif zone_category == "yellow" and gap_fair_pct >= 4:
                score += 20
                categories.add(OPPORTUNITY_CATEGORY)
                reasons.append(
                    f"Fair-value zone trading {gap_fair_pct:.0f}% below fair-yield price"
                )

        if rating in {"BUY", "STRONG BUY", "OUTPERFORM"}:
            score += 10
            categories.add(OPPORTUNITY_CATEGORY)
            reasons.append(f"Analyst view: {row.analyst_rating}")

        if row.growth_years and row.growth_years >= 25:
            score += 8
            reasons.append(f"{row.growth_years} consecutive years of dividend growth")

        stock = preload.stock_data.get(row.ticker)
        if stock and stock.dividend_safety_score is not None and stock.dividend_safety_score >= 65:
            score += 8
            reasons.append(f"Dividend safety {stock.dividend_safety_score:.0f}/100")

        if row.profit_pct is not None and row.profit_pct >= 0:
            score += 4

        if score < OPPORTUNITY_MIN_SCORE or OPPORTUNITY_CATEGORY not in categories:
            return None

        severity = "high" if score >= OPPORTUNITY_HIGH_SCORE else "medium"
        return score, severity, categories, reasons[:5]

    def to_dataframe(
        self,
        summary: AttentionSummary | None,
        *,
        list_kind: str = "risk",
    ) -> pd.DataFrame:
        import pandas as pd

        summary = normalize_attention_summary(summary)
        if summary is None:
            return pd.DataFrame()

        if list_kind == "dividend":
            items = summary.dividend_items
            return pd.DataFrame(
                [
                    {
                        "Ticker": item.symbol,
                        "Company": item.company,
                        "Timing": item.timing or "—",
                        "Ex-Date": item.ex_date,
                        "Pay Date": item.pay_date,
                        "Details": " • ".join(item.reasons),
                    }
                    for item in items
                ]
            )
        items = summary.opportunity_items if list_kind == "opportunity" else summary.risk_items
        return pd.DataFrame(
            [
                {
                    "Ticker": item.symbol,
                    "Company": item.company,
                    "Severity": item.severity.title(),
                    "Score": item.score,
                    "Categories": ", ".join(item.categories),
                    "Reasons": " • ".join(item.reasons),
                    "Weight %": item.portfolio_weight_pct,
                    "Profit %": item.profit_pct,
                }
                for item in items
            ]
        )

    def fetch_news_for_symbols(
        self,
        symbols: Sequence[str],
        *,
        max_symbols: int = 15,
        max_workers: int = 4,
    ) -> dict[str, NewsSummary]:
        """Fetch recent news summaries for a limited symbol list (network)."""
        from services.news_service import NewsService

        unique = list(dict.fromkeys(symbols))[:max_symbols]
        if not unique:
            return {}

        service = NewsService(days=7)
        results: dict[str, NewsSummary] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(service.fetch_news_summary, symbol, max_articles=8): symbol
                for symbol in unique
            }
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    results[symbol] = future.result()
                except Exception:  # noqa: BLE001, S112
                    continue
        return results
