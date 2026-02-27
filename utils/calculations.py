"""
Shared financial calculation utilities.

This module provides consistent calculation functions used across
services for dividend analysis. All functions handle None values
gracefully and return None when calculation is not possible.
"""

from __future__ import annotations

from typing import Optional, List
from datetime import date


def calculate_cagr(
    start_value: float,
    end_value: float,
    years: int,
) -> float:
    """
    Calculate Compound Annual Growth Rate.
    
    CAGR represents the mean annual growth rate over a specified
    time period, assuming profits are reinvested at the end of each year.
    
    Args:
        start_value: Starting value (must be positive).
        end_value: Ending value (must be positive).
        years: Number of years (must be >= 1).
        
    Returns:
        CAGR as a percentage (e.g., 5.5 for 5.5% growth).
        Returns 0.0 if calculation is not possible.
        
    Example:
        >>> calculate_cagr(100, 150, 5)
        8.45  # 8.45% annual growth
    """
    if start_value <= 0 or end_value <= 0 or years < 1:
        return 0.0
    
    try:
        return ((end_value / start_value) ** (1 / years) - 1) * 100
    except (ValueError, ZeroDivisionError, OverflowError):
        return 0.0


def calculate_dividend_yield(
    dividend_rate: Optional[float],
    price: Optional[float],
) -> Optional[float]:
    """
    Calculate dividend yield percentage.
    
    Dividend yield is the annual dividend payment divided by the
    stock price, expressed as a percentage.
    
    Args:
        dividend_rate: Annual dividend per share (dollars).
        price: Current stock price (dollars).
        
    Returns:
        Yield as percentage (e.g., 3.5 for 3.5%), or None if not calculable.
        
    Example:
        >>> calculate_dividend_yield(2.00, 50.00)
        4.0  # 4.0% yield
    """
    if dividend_rate is None or price is None or price <= 0:
        return None
    if dividend_rate < 0:
        return None
    return (dividend_rate / price) * 100


def calculate_payout_ratio(
    dividend_rate: Optional[float],
    eps: Optional[float],
) -> Optional[float]:
    """
    Calculate dividend payout ratio.
    
    The payout ratio shows what percentage of earnings is paid out
    as dividends. Lower ratios generally indicate more sustainable
    dividends with room for growth.
    
    Args:
        dividend_rate: Annual dividend per share (dollars).
        eps: Earnings per share (dollars).
        
    Returns:
        Payout ratio as percentage, or None if not calculable.
        
    Example:
        >>> calculate_payout_ratio(1.50, 4.00)
        37.5  # 37.5% payout ratio
    """
    if dividend_rate is None or eps is None or eps <= 0:
        return None
    if dividend_rate < 0:
        return None
    return (dividend_rate / eps) * 100


def calculate_dividend_coverage(
    eps: Optional[float],
    dividend_rate: Optional[float],
) -> Optional[float]:
    """
    Calculate dividend coverage ratio.
    
    Shows how many times earnings cover the dividend payment.
    Higher coverage indicates greater dividend safety.
    
    Args:
        eps: Earnings per share (dollars).
        dividend_rate: Annual dividend per share (dollars).
        
    Returns:
        Coverage ratio (e.g., 2.5 means EPS is 2.5x the dividend),
        or None if not calculable.
        
    Example:
        >>> calculate_dividend_coverage(4.00, 1.50)
        2.67  # Earnings cover dividend 2.67 times
        
    Note:
        - Coverage >= 2.0 is generally considered safe
        - Coverage >= 1.5 is acceptable
        - Coverage < 1.0 means dividend exceeds earnings (unsustainable)
    """
    if eps is None or dividend_rate is None or dividend_rate <= 0:
        return None
    return eps / dividend_rate


def calculate_price_to_target_pct(
    current_price: Optional[float],
    target_price: Optional[float],
) -> Optional[float]:
    """
    Calculate percentage upside/downside to analyst target price.
    
    Args:
        current_price: Current stock price (dollars).
        target_price: Analyst target price (dollars).
        
    Returns:
        Percentage difference (positive = upside potential,
        negative = downside risk), or None if not calculable.
        
    Example:
        >>> calculate_price_to_target_pct(100, 120)
        20.0  # 20% upside potential
    """
    if current_price is None or target_price is None or current_price <= 0:
        return None
    return ((target_price / current_price) - 1) * 100


def calculate_income_per_investment(
    investment_amount: float,
    dividend_yield_pct: Optional[float],
) -> Optional[float]:
    """
    Calculate annual dividend income from an investment amount.
    
    Args:
        investment_amount: Amount invested (dollars).
        dividend_yield_pct: Current dividend yield (percentage).
        
    Returns:
        Annual dividend income (dollars), or None if not calculable.
        
    Example:
        >>> calculate_income_per_investment(10000, 3.5)
        350.0  # $350 annual income from $10,000 investment
    """
    if dividend_yield_pct is None or investment_amount <= 0:
        return None
    if dividend_yield_pct < 0:
        return None
    return investment_amount * (dividend_yield_pct / 100)


def calculate_years_to_double(
    growth_rate_pct: Optional[float],
) -> Optional[float]:
    """
    Calculate years to double investment using Rule of 72.
    
    Args:
        growth_rate_pct: Annual growth rate (percentage).
        
    Returns:
        Approximate years to double, or None if not calculable.
        
    Example:
        >>> calculate_years_to_double(8.0)
        9.0  # Takes ~9 years to double at 8% growth
    """
    if growth_rate_pct is None or growth_rate_pct <= 0:
        return None
    return 72 / growth_rate_pct
