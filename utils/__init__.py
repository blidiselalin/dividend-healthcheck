"""
Shared utilities for dividend analysis.

This package provides common utilities used across the application:
- formatting: Display formatting functions
- calculations: Financial calculation functions
- converters: Data model conversion functions
"""

from .calculations import (
    calculate_cagr,
    calculate_dividend_coverage,
    calculate_dividend_yield,
    calculate_income_per_investment,
    calculate_payout_ratio,
    calculate_price_to_target_pct,
    calculate_years_to_double,
)
from .converters import (
    FREQUENCY_ANNUAL,
    FREQUENCY_MONTHLY,
    FREQUENCY_QUARTERLY,
    FREQUENCY_SEMI_ANNUAL,
    detect_payment_frequency,
    document_to_stock_data,
)
from .formatting import (
    format_currency,
    format_delta,
    format_delta_pct,
    format_large_number,
    format_number,
    format_percent,
    format_years,
)

__all__ = [
    "FREQUENCY_ANNUAL",
    "FREQUENCY_MONTHLY",
    "FREQUENCY_QUARTERLY",
    "FREQUENCY_SEMI_ANNUAL",
    "calculate_cagr",
    "calculate_dividend_coverage",
    "calculate_dividend_yield",
    "calculate_income_per_investment",
    "calculate_payout_ratio",
    "calculate_price_to_target_pct",
    "calculate_years_to_double",
    "detect_payment_frequency",
    "document_to_stock_data",
    "format_currency",
    "format_delta",
    "format_delta_pct",
    "format_large_number",
    "format_number",
    "format_percent",
    "format_years",
]
