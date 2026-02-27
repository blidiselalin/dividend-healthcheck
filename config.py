"""
Configuration and constants for Dividend Kings Analysis.

This module contains all configurable parameters including stock lists,
scoring weights, thresholds, and data provider settings.
"""

from typing import Dict, List, Final

# Dividend stocks for analysis - including Kings (50+ years) and high-quality payers
DIVIDEND_KINGS: Final[List[str]] = [
    "ABBV", "ADM", "ADP", "AFG", "AMAT", "AMT", "ARCC", "ARE", "AWK",
    "BAC", "BBY", "BEN", "BMY", "BTI",
    "CMCSA", "CSCO",
    "DVN",
    "ESS",
    "HSY",
    "IBM",
    "JNJ",
    "KO",
    "MDLZ", "MDT", "MMM", "MO",
    "NEE", "NKE", "NNN", "NSP",
    "O",
    "PEP", "PRU",
    "QCOM",
    "SBUX", "SWK", "SWKS",
    "T", "TROW",
    "UGI",
    "VSNT", "VZ",
    "WPC",
    "XOM",
    "ZTS",
]

# Dividend Aristocrats for comparison (25+ years)
DIVIDEND_ARISTOCRATS: Final[List[str]] = [
    "ABBV", "ADM", "ADP", "AFL", "ALB", "AMCR", "AOS", "APD", "ATO", "BDX",
    "BEN", "BF.B", "BRO", "CAH", "CAT", "CB", "CHRW", "CINF", "CLX", "CTAS",
    "CVX", "ECL", "ED", "ESS", "EXPD", "FAST", "FDS", "GD", "IBM", "KMB",
    "LIN", "MCD", "MDT", "MKC", "NEE", "NUE", "O", "PEP", "ROP", "SPGI",
    "T", "TROW", "VFC", "WBA", "WMT", "WST", "XOM",
]

# Combined list for full analysis
ALL_DIVIDEND_STOCKS: Final[List[str]] = sorted(set(DIVIDEND_KINGS + DIVIDEND_ARISTOCRATS))

# Dividend streak tiers
DIVIDEND_TIERS: Final[Dict[str, int]] = {
    "king": 50,        # 50+ years
    "aristocrat": 25,  # 25+ years
    "achiever": 10,    # 10+ years
    "contender": 5,    # 5+ years
}

# Scoring weights - total = 100 points (investor-focused)
SCORING_WEIGHTS: Final[Dict[str, int]] = {
    "dividend_streak": 20,      # Years of consecutive increases (core criterion)
    "dividend_safety": 15,      # Payout ratio sustainability
    "dividend_yield": 15,       # Current income potential
    "dividend_growth": 15,      # CAGR of dividend increases
    "valuation": 10,            # P/E, forward P/E
    "financial_strength": 10,   # Debt levels, coverage ratios
    "profitability": 10,        # ROE, margins
    "size_stability": 5,        # Market cap (larger = more stable)
}

# Recommendation score thresholds
RECOMMENDATION_THRESHOLDS: Final[Dict[str, int]] = {
    "strong_buy": 80,
    "buy": 65,
    "accumulate": 50,
    "hold": 35,
}

# Data validation thresholds
MAX_DIVIDEND_YIELD_PCT: Final[float] = 15.0
MAX_PAYOUT_RATIO_PCT: Final[float] = 200.0

# API rate limiting (seconds between requests)
API_DELAY_SECONDS: Final[float] = 0.2

# Data source attribution (masked as aggregated public sources)
DATA_SOURCES: Final[Dict[str, str]] = {
    "primary": "Market Data Aggregator",
    "fundamentals": "Public Financial Filings",
    "analyst": "Consensus Estimates",
    "historical": "Exchange Data",
}
