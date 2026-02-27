"""
Shared financial calculation utilities.

This module provides consistent calculation functions used across
services for dividend analysis.
"""

from typing import Optional


def calculate_cagr(
    start_value: float,
    end_value: float,
    years: int
) -> float:
    """
    Calculate Compound Annual Growth Rate.
    
    Args:
        start_value: Starting value
        end_value: Ending value
        years: Number of years
        
    Returns:
        CAGR as a percentage (e.g., 5.5 for 5.5%)
    """
    if start_value <= 0 or end_value <= 0 or years < 1:
        return 0.0
    return ((end_value / start_value) ** (1 / years) - 1) * 100


def calculate_dividend_yield(
    dividend_rate: Optional[float],
    price: Optional[float]
) -> Optional[float]:
    """
    Calculate dividend yield percentage.
    
    Args:
        dividend_rate: Annual dividend per share
        price: Current stock price
        
    Returns:
        Yield as percentage or None if calculation not possible
    """
    if dividend_rate is None or price is None or price <= 0:
        return None
    return (dividend_rate / price) * 100


def calculate_payout_ratio(
    dividend_rate: Optional[float],
    eps: Optional[float]
) -> Optional[float]:
    """
    Calculate dividend payout ratio.
    
    Args:
        dividend_rate: Annual dividend per share
        eps: Earnings per share
        
    Returns:
        Payout ratio as percentage or None
    """
    if dividend_rate is None or eps is None or eps <= 0:
        return None
    return (dividend_rate / eps) * 100


def calculate_dividend_coverage(
    eps: Optional[float],
    dividend_rate: Optional[float]
) -> Optional[float]:
    """
    Calculate how many times earnings cover the dividend.
    
    Args:
        eps: Earnings per share
        dividend_rate: Annual dividend per share
        
    Returns:
        Coverage ratio (e.g., 2.5x) or None
    """
    if eps is None or dividend_rate is None or dividend_rate <= 0:
        return None
    return eps / dividend_rate


def calculate_price_to_target_pct(
    current_price: Optional[float],
    target_price: Optional[float]
) -> Optional[float]:
    """
    Calculate percentage difference from target price.
    
    Args:
        current_price: Current stock price
        target_price: Target price
        
    Returns:
        Percentage upside/downside or None
    """
    if current_price is None or target_price is None or current_price <= 0:
        return None
    return ((target_price / current_price) - 1) * 100
