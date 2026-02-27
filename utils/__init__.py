"""
Shared utilities for dividend analysis.

This package provides common utilities used across the application:
- formatting: Display formatting functions
- calculations: Financial calculation functions
- converters: Data model conversion functions
"""

from .formatting import (
    format_currency,
    format_percent,
    format_number,
    format_large_number,
    format_years,
    format_delta,
    format_delta_pct,
)

from .calculations import (
    calculate_cagr,
    calculate_dividend_yield,
    calculate_payout_ratio,
    calculate_dividend_coverage,
    calculate_price_to_target_pct,
    calculate_income_per_investment,
    calculate_years_to_double,
)

from .converters import (
    document_to_stock_data,
    detect_payment_frequency,
    FREQUENCY_MONTHLY,
    FREQUENCY_QUARTERLY,
    FREQUENCY_SEMI_ANNUAL,
    FREQUENCY_ANNUAL,
)

__all__ = [
    # Formatting
    "format_currency",
    "format_percent",
    "format_number",
    "format_large_number",
    "format_years",
    "format_delta",
    "format_delta_pct",
    # Calculations
    "calculate_cagr",
    "calculate_dividend_yield",
    "calculate_payout_ratio",
    "calculate_dividend_coverage",
    "calculate_price_to_target_pct",
    "calculate_income_per_investment",
    "calculate_years_to_double",
    # Converters
    "document_to_stock_data",
    "detect_payment_frequency",
    "FREQUENCY_MONTHLY",
    "FREQUENCY_QUARTERLY",
    "FREQUENCY_SEMI_ANNUAL",
    "FREQUENCY_ANNUAL",
]
