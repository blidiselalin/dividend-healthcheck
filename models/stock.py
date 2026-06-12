"""
Stock data models.

This module defines the data structures used to represent stock information
with a focus on dividend investing metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True)
class DividendHistory:
    """
    Historical dividend data with detailed metrics.

    This immutable dataclass stores comprehensive dividend history
    including growth rates and payment patterns.

    Attributes:
        consecutive_years: Years of consecutive dividend increases (key metric).
        total_years: Total years of dividend data available.
        cagr_5y: 5-year Compound Annual Growth Rate (percentage).
        cagr_10y: 10-year Compound Annual Growth Rate (percentage).
        current_annual: Current annual dividend per share (dollars).
        ex_dividend_date: Next ex-dividend date.
        payment_frequency: Dividends per year (12=monthly, 4=quarterly, 2=semi, 1=annual).
    """

    consecutive_years: int
    total_years: int
    cagr_5y: float
    cagr_10y: float
    current_annual: float
    ex_dividend_date: date | None = None
    payment_frequency: int = 4

    def __post_init__(self) -> None:
        """Validate fields after initialization."""
        if self.consecutive_years < 0:
            object.__setattr__(self, "consecutive_years", 0)
        if self.total_years < 0:
            object.__setattr__(self, "total_years", 0)
        if self.payment_frequency not in (1, 2, 4, 12):
            object.__setattr__(self, "payment_frequency", 4)


@dataclass
class StockData:
    """
    Comprehensive stock data optimized for dividend investors.

    Organized by importance: dividend metrics first, then valuation,
    financial health, and supplementary data.

    Attributes are grouped into categories:
    - Core Identity: symbol, name, sector, industry
    - Dividend Metrics: yield, payout ratio, history
    - Price & Valuation: PE ratios, price/book, etc.
    - Financial Health: debt ratios, liquidity
    - Profitability: ROE, margins
    - Growth: revenue, earnings growth
    - Analyst Data: ratings, price targets
    - Performance: returns
    - Metadata: data sources, quality score
    """

    # === CORE IDENTITY ===
    symbol: str
    name: str
    sector: str
    industry: str

    # === DIVIDEND METRICS (Most Important for Dividend Investors) ===
    dividend_yield_pct: float | None = None
    dividend_rate: float | None = None
    payout_ratio_pct: float | None = None
    dividend_history: DividendHistory | None = None

    # Dividend safety indicators
    fcf_payout_ratio_pct: float | None = None
    dividend_coverage: float | None = None

    # === PRICE & VALUATION ===
    price: float | None = None
    market_cap: float | None = None
    trailing_pe: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    ev_ebitda: float | None = None

    # Price context
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    price_to_52w_high_pct: float | None = None

    # === FINANCIAL HEALTH ===
    debt_to_equity: float | None = None
    debt_to_ebitda: float | None = None
    interest_coverage: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None

    # === PROFITABILITY ===
    roe_pct: float | None = None
    roa_pct: float | None = None
    roic_pct: float | None = None
    profit_margin_pct: float | None = None
    operating_margin_pct: float | None = None
    gross_margin_pct: float | None = None

    # === GROWTH ===
    revenue_growth_pct: float | None = None
    earnings_growth_pct: float | None = None
    fcf_growth_pct: float | None = None

    # === ANALYST & MARKET DATA ===
    beta: float | None = None
    target_price: float | None = None
    target_upside_pct: float | None = None
    analyst_rating: str | None = None
    num_analysts: int | None = None

    # === PERFORMANCE ===
    price_return_1y: float | None = None
    total_return_1y: float | None = None
    price_return_5y: float | None = None

    # === DATA SOURCE TRACKING ===
    data_sources: list[str] = field(default_factory=list)
    data_quality_score: float | None = None

    # Private: last update timestamp (set by converters)
    _last_updated: datetime | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate and normalize fields after initialization."""
        # Ensure symbol is uppercase
        self.symbol = self.symbol.upper().strip()

        # Ensure name has a value
        if not self.name:
            self.name = self.symbol

    @property
    def dividend_tier(self) -> str:
        """
        Get dividend tier based on consecutive years.

        Returns:
            Tier name: "King", "Aristocrat", "Achiever", "Contender", or "Starter".
        """
        if not self.dividend_history:
            return "Unknown"

        years = self.dividend_history.consecutive_years

        if years >= 50:
            return "King"
        if years >= 25:
            return "Aristocrat"
        if years >= 10:
            return "Achiever"
        if years >= 5:
            return "Contender"
        return "Starter"

    @property
    def is_dividend_king(self) -> bool:
        """Check if stock qualifies as Dividend King (50+ years)."""
        return self.dividend_history is not None and self.dividend_history.consecutive_years >= 50

    @property
    def is_dividend_aristocrat(self) -> bool:
        """Check if stock qualifies as Dividend Aristocrat (25+ years)."""
        return self.dividend_history is not None and self.dividend_history.consecutive_years >= 25

    @property
    def dividend_safety_score(self) -> float | None:
        """
        Calculate dividend safety score (0-100) based on payout ratios.

        Lower payout ratios indicate safer, more sustainable dividends.
        The score is adjusted if FCF coverage data is available.

        Returns:
            Safety score from 0-100, or None if payout ratio unavailable.
        """
        if self.payout_ratio_pct is None:
            return None

        # Lower payout ratio = safer dividend
        if self.payout_ratio_pct <= 40:
            base_score = 100.0
        elif self.payout_ratio_pct <= 60:
            base_score = 85.0
        elif self.payout_ratio_pct <= 75:
            base_score = 70.0
        elif self.payout_ratio_pct <= 90:
            base_score = 50.0
        else:
            base_score = max(0.0, 100.0 - self.payout_ratio_pct)

        # Adjust for FCF coverage if available
        if self.fcf_payout_ratio_pct is not None:
            if self.fcf_payout_ratio_pct <= 60:
                base_score = min(100.0, base_score + 10)
            elif self.fcf_payout_ratio_pct > 100:
                base_score = max(0.0, base_score - 20)

        return base_score

    @property
    def annual_income_per_10k(self) -> float | None:
        """
        Calculate annual dividend income from a $10,000 investment.

        Returns:
            Annual income in dollars, or None if yield unavailable.
        """
        if self.dividend_yield_pct is None:
            return None
        return 10_000 * (self.dividend_yield_pct / 100)

    @property
    def has_complete_dividend_data(self) -> bool:
        """Check if essential dividend data is present."""
        return (
            self.dividend_yield_pct is not None
            and self.dividend_history is not None
            and self.dividend_history.consecutive_years > 0
        )
