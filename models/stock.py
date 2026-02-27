"""
Stock data models.

This module defines the data structures used to represent stock information
with a focus on dividend investing metrics.
"""

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import date


@dataclass(frozen=True)
class DividendHistory:
    """Historical dividend data with detailed metrics.
    
    Attributes:
        consecutive_years: Years of consecutive dividend increases (key metric).
        total_years: Total years of dividend data available.
        cagr_5y: 5-year Compound Annual Growth Rate.
        cagr_10y: 10-year Compound Annual Growth Rate.
        current_annual: Current annual dividend per share.
        ex_dividend_date: Next ex-dividend date.
        payment_frequency: Dividends per year (typically 4 for quarterly).
    """
    consecutive_years: int
    total_years: int
    cagr_5y: float
    cagr_10y: float
    current_annual: float
    ex_dividend_date: Optional[date] = None
    payment_frequency: int = 4


@dataclass
class StockData:
    """Comprehensive stock data optimized for dividend investors.
    
    Organized by importance: dividend metrics first, then valuation,
    financial health, and supplementary data.
    """
    
    # === CORE IDENTITY ===
    symbol: str
    name: str
    sector: str
    industry: str
    
    # === DIVIDEND METRICS (Most Important for Dividend Investors) ===
    dividend_yield_pct: Optional[float] = None
    dividend_rate: Optional[float] = None
    payout_ratio_pct: Optional[float] = None
    dividend_history: Optional[DividendHistory] = None
    
    # Dividend safety indicators
    fcf_payout_ratio_pct: Optional[float] = None  # Dividend / Free Cash Flow
    dividend_coverage: Optional[float] = None      # EPS / Dividend
    
    # === PRICE & VALUATION ===
    price: Optional[float] = None
    market_cap: Optional[float] = None
    trailing_pe: Optional[float] = None
    forward_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    price_to_book: Optional[float] = None
    price_to_sales: Optional[float] = None
    ev_ebitda: Optional[float] = None
    
    # Price context
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    price_to_52w_high_pct: Optional[float] = None  # How far from 52w high
    
    # === FINANCIAL HEALTH ===
    debt_to_equity: Optional[float] = None
    debt_to_ebitda: Optional[float] = None
    interest_coverage: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    
    # === PROFITABILITY ===
    roe_pct: Optional[float] = None
    roa_pct: Optional[float] = None
    roic_pct: Optional[float] = None
    profit_margin_pct: Optional[float] = None
    operating_margin_pct: Optional[float] = None
    gross_margin_pct: Optional[float] = None
    
    # === GROWTH ===
    revenue_growth_pct: Optional[float] = None
    earnings_growth_pct: Optional[float] = None
    fcf_growth_pct: Optional[float] = None
    
    # === ANALYST & MARKET DATA ===
    beta: Optional[float] = None
    target_price: Optional[float] = None
    target_upside_pct: Optional[float] = None
    analyst_rating: Optional[str] = None
    num_analysts: Optional[int] = None
    
    # === PERFORMANCE ===
    price_return_1y: Optional[float] = None
    total_return_1y: Optional[float] = None  # Price + dividends
    price_return_5y: Optional[float] = None
    
    # === DATA SOURCE TRACKING ===
    data_sources: List[str] = field(default_factory=list)
    data_quality_score: Optional[float] = None  # 0-100 completeness
    
    @property
    def dividend_tier(self) -> str:
        """Get dividend tier based on consecutive years."""
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
        return (
            self.dividend_history is not None 
            and self.dividend_history.consecutive_years >= 50
        )
    
    @property
    def dividend_safety_score(self) -> Optional[float]:
        """Calculate dividend safety score (0-100) based on payout ratios."""
        if self.payout_ratio_pct is None:
            return None
        
        # Lower payout ratio = safer dividend
        if self.payout_ratio_pct <= 40:
            base_score = 100
        elif self.payout_ratio_pct <= 60:
            base_score = 85
        elif self.payout_ratio_pct <= 75:
            base_score = 70
        elif self.payout_ratio_pct <= 90:
            base_score = 50
        else:
            base_score = max(0, 100 - self.payout_ratio_pct)
        
        # Adjust for FCF coverage if available
        if self.fcf_payout_ratio_pct is not None:
            if self.fcf_payout_ratio_pct <= 60:
                base_score = min(100, base_score + 10)
            elif self.fcf_payout_ratio_pct > 100:
                base_score = max(0, base_score - 20)
        
        return base_score
