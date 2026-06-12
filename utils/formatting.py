"""
Shared formatting utilities for dividend analysis.

This module provides consistent formatting functions used across
the UI, reports, and data export.
"""

from __future__ import annotations


def format_currency(value: float | None, decimals: int = 2) -> str:
    """Format value as currency string."""
    if value is None:
        return "N/A"
    return f"${value:,.{decimals}f}"


def format_percent(value: float | None, decimals: int = 1) -> str:
    """Format value as percentage string."""
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}%"


def format_number(value: float | None, decimals: int = 1) -> str:
    """Format numeric value as string."""
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}"


def format_large_number(value: float | None) -> str:
    """Format large numbers with B/M/T suffix (e.g., market cap)."""
    if value is None:
        return "N/A"
    if value >= 1e12:
        return f"${value / 1e12:.2f}T"
    if value >= 1e9:
        return f"${value / 1e9:.1f}B"
    if value >= 1e6:
        return f"${value / 1e6:.1f}M"
    return f"${value:,.0f}"


def format_years(value: int | None) -> str:
    """Format years with suffix."""
    if value is None:
        return "N/A"
    return f"{value} yrs"


def format_delta(value: float | None, decimals: int = 2) -> str:
    """Format value as delta with +/- sign."""
    if value is None:
        return "N/A"
    return f"{value:+.{decimals}f}"


def format_delta_pct(value: float | None, decimals: int = 1) -> str:
    """Format value as percentage delta with +/- sign."""
    if value is None:
        return "N/A"
    return f"{value:+.{decimals}f}%"
