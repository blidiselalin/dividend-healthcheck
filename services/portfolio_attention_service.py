"""
Flag portfolio holdings: dividend timing (separate list) vs negative risk signals.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

from data_ingestion.portfolio_store import PortfolioStore
from services.portfolio_dividend_calendar import build_portfolio_dividend_calendar
from services.portfolio_details_service import PortfolioDetailRow
from services.portfolio_zone_overview import zone_to_category

if TYPE_CHECKING:
    from services.portfolio_analysis_preload import PortfolioAnalysisPreload
    from services.news_service import NewsSummary

EX_DATE_SOON_DAYS = 21
OVERWEIGHT_WEIGHT_PCT = 8.0
PROFIT_WARN_PCT = -8.0
PROFIT_ALERT_PCT = -18.0
DECLINE_180_WARN_PCT = -12.0
DECLINE_365_WARN_PCT = -18.0
TARGET_DOWNSIDE_WARN_PCT = -12.0

DIVIDEND_CATEGORY = "Dividend"
NEGATIVE_CATEGORIES = frozenset({"Exposure", "Estimates", "News"})


@dataclass(frozen=True)
class AttentionItem:
    symbol: str
    company: str
    severity: str  # high | medium | low
    score: int
    categories: tuple[str, ...]
    reasons: tuple[str, ...]
    portfolio_weight_pct: Optional[float] = None
    profit_pct: Optional[float] = None


@dataclass
class AttentionSummary:
    """Risk watchlist (negative) and dividend attention (timing / cash) are separate."""

    risk_items: List[AttentionItem] = field(default_factory=list)
    dividend_items: List[AttentionItem] = field(default_factory=list)
    reference_date: date = field(default_factory=date.today)

    @property
    def items(self) -> List[AttentionItem]:
        """Backward compatibility: attention watchlist = risk only."""
        return self.risk_items

    @property
    def total(self) -> int:
        return len(self.risk_items)

    @property
    def dividend_total(self) -> int:
        return len(self.dividend_items)

    @property
    def high_count(self) -> int:
        return sum(1 for item in self.risk_items if item.severity == "high")

    @property
    def dividend_high_count(self) -> int:
        return sum(1 for item in self.dividend_items if item.severity == "high")

    @property
    def by_category(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in self.risk_items:
            for category in item.categories:
                counts[category] = counts.get(category, 0) + 1
        return counts


def split_legacy_attention_items(
    items: Sequence[AttentionItem],
    reference_date: Optional[date] = None,
) -> AttentionSummary:
    """Convert pre-split cached items into risk + dividend lists."""
    risk_items: List[AttentionItem] = []
    dividend_items: List[AttentionItem] = []
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


def normalize_attention_summary(summary: Any) -> Optional[AttentionSummary]:
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
        preload: "PortfolioAnalysisPreload",
        *,
        reference_date: Optional[date] = None,
        news_by_symbol: Optional[Dict[str, "NewsSummary"]] = None,
    ) -> AttentionSummary:
        today = reference_date or date.today()
        holdings = PortfolioStore().list_holdings()
        row_dates = {
            row.ticker: (row.ex_dividend_date, row.dividend_pay_date) for row in rows
        }
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

        risk_scored: List[AttentionItem] = []
        dividend_scored: List[AttentionItem] = []
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
            if dividend_flags:
                score, severity, reasons = dividend_flags
                dividend_scored.append(
                    AttentionItem(
                        symbol=row.ticker,
                        company=row.company,
                        severity=severity,
                        score=score,
                        categories=(DIVIDEND_CATEGORY,),
                        reasons=tuple(reasons),
                        portfolio_weight_pct=row.weight_pct,
                        profit_pct=row.profit_pct,
                    )
                )
            if risk_flags:
                score, severity, categories, reasons = risk_flags
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

        risk_scored.sort(key=lambda item: (-item.score, item.symbol))
        dividend_scored.sort(key=lambda item: (-item.score, item.symbol))
        return AttentionSummary(
            risk_items=risk_scored,
            dividend_items=dividend_scored,
            reference_date=today,
        )

    def _evaluate_dividend_attention(
        self,
        row: PortfolioDetailRow,
        *,
        today: date,
        current_payers: set[str],
        next_payers: set[str],
        scheduled_now: set[str],
    ) -> Optional[tuple[int, str, List[str]]]:
        score = 0
        reasons: List[str] = []

        if row.ex_dividend_date:
            days_to_ex = (row.ex_dividend_date - today).days
            if 0 <= days_to_ex <= 7:
                score += 35
                reasons.append(
                    f"Ex-dividend in {days_to_ex} day(s) ({row.ex_dividend_date:%d %b})"
                )
            elif 0 <= days_to_ex <= EX_DATE_SOON_DAYS:
                score += 22
                reasons.append(f"Ex-dividend within {days_to_ex} days")

        if row.ticker in scheduled_now:
            score += 18
            reasons.append("Dividend payment scheduled or projected this month")
        elif row.ticker in current_payers and row.ticker not in scheduled_now:
            score += 10
            reasons.append("Dividend cash expected this month")
        elif row.ticker in next_payers:
            score += 8
            reasons.append("Dividend expected next month")

        if score < 8 or not reasons:
            return None

        severity = "high" if score >= 35 else "medium" if score >= 18 else "low"
        return score, severity, reasons[:5]

    def _evaluate_risk_attention(
        self,
        row: PortfolioDetailRow,
        *,
        preload: "PortfolioAnalysisPreload",
        news: Optional["NewsSummary"],
    ) -> Optional[tuple[int, str, set[str], List[str]]]:
        score = 0
        categories: set[str] = set()
        reasons: List[str] = []

        channel = preload.yield_channels.get(row.ticker)
        if channel:
            category = zone_to_category(channel.zone)
            if category == "red":
                score += 28
                categories.add("Exposure")
                reasons.append(f"Yield zone: {channel.zone} (expensive vs history)")
            elif category == "yellow" and row.profit_pct is not None and row.profit_pct < 0:
                score += 10
                categories.add("Exposure")
                reasons.append(
                    f"Fair-value zone with unrealized loss ({row.profit_pct:+.1f}%)"
                )

            if channel.current_price and channel.fair_value_price:
                gap_pct = ((channel.fair_value_price / channel.current_price) - 1) * 100
                if gap_pct < -12:
                    score += 14
                    categories.add("Exposure")
                    reasons.append(f"Price {abs(gap_pct):.0f}% above fair-value yield level")

        if row.weight_pct is not None and row.weight_pct >= OVERWEIGHT_WEIGHT_PCT:
            if categories.intersection({"Exposure"}) or (
                row.profit_pct is not None and row.profit_pct < 0
            ):
                score += 12
                categories.add("Exposure")
                reasons.append(f"Large position ({row.weight_pct:.1f}% of portfolio)")

        if row.profit_pct is not None:
            if row.profit_pct <= PROFIT_ALERT_PCT:
                score += 30
                categories.add("Exposure")
                reasons.append(f"Large unrealized loss ({row.profit_pct:+.1f}%)")
            elif row.profit_pct <= PROFIT_WARN_PCT:
                score += 16
                categories.add("Exposure")
                reasons.append(f"Unrealized loss ({row.profit_pct:+.1f}%)")

        if row.change_365d_pct is not None and row.change_365d_pct <= DECLINE_365_WARN_PCT:
            score += 18
            categories.add("Exposure")
            reasons.append(f"Price down {abs(row.change_365d_pct):.1f}% vs 1 year ago")
        elif row.change_180d_pct is not None and row.change_180d_pct <= DECLINE_180_WARN_PCT:
            score += 12
            categories.add("Exposure")
            reasons.append(f"Price down {abs(row.change_180d_pct):.1f}% vs 6 months ago")

        rating = (row.analyst_rating or "").upper()
        if rating in {"AVOID", "SELL", "STRONG SELL", "UNDERPERFORM"}:
            score += 32
            categories.add("Estimates")
            reasons.append(f"Analyst view: {row.analyst_rating}")
        elif rating in {"WEAK HOLD", "HOLD/WATCH"} and row.profit_pct is not None and row.profit_pct < 0:
            score += 14
            categories.add("Estimates")
            reasons.append(f"Neutral analyst view with loss ({row.analyst_rating})")

        stock = preload.stock_data.get(row.ticker)
        if stock and stock.target_upside_pct is not None:
            if stock.target_upside_pct <= TARGET_DOWNSIDE_WARN_PCT:
                score += 24
                categories.add("Estimates")
                reasons.append(f"Price target implies {stock.target_upside_pct:+.1f}% downside")
            elif stock.target_upside_pct < 0:
                score += 12
                categories.add("Estimates")
                reasons.append(f"Below consensus target ({stock.target_upside_pct:+.1f}%)")

        if stock and stock.earnings_growth_pct is not None and stock.earnings_growth_pct < -10:
            score += 10
            categories.add("Estimates")
            reasons.append(f"Earnings growth estimate {stock.earnings_growth_pct:+.1f}%")

        if news:
            if news.overall_sentiment in ("bearish",) or news.sentiment_score <= -0.35:
                score += 26
                categories.add("News")
                reasons.append(f"Recent news sentiment: {news.overall_sentiment}")
            elif news.negative_count > news.positive_count and news.negative_count >= 2:
                score += 16
                categories.add("News")
                reasons.append(
                    f"More negative than positive headlines "
                    f"({news.negative_count} vs {news.positive_count})"
                )
            if news.risks:
                score += 8
                categories.add("News")
                reasons.append(news.risks[0][:120])

        if score < 8 or not categories:
            return None

        severity = "high" if score >= 40 else "medium" if score >= 20 else "low"
        return score, severity, categories, reasons[:5]

    def to_dataframe(
        self,
        summary: Optional[AttentionSummary],
        *,
        list_kind: str = "risk",
    ):
        import pandas as pd

        summary = normalize_attention_summary(summary)
        if summary is None:
            return pd.DataFrame()

        items = (
            summary.dividend_items if list_kind == "dividend" else summary.risk_items
        )
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
    ) -> Dict[str, "NewsSummary"]:
        """Fetch recent news summaries for a limited symbol list (network)."""
        from services.news_service import NewsService

        unique = list(dict.fromkeys(symbols))[:max_symbols]
        if not unique:
            return {}

        service = NewsService(days=7)
        results: Dict[str, "NewsSummary"] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(service.fetch_news_summary, symbol, max_articles=8): symbol
                for symbol in unique
            }
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    results[symbol] = future.result()
                except Exception:
                    continue
        return results
