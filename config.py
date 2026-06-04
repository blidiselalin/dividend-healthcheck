"""
Configuration and constants for DividendScope.

This module contains all configurable parameters including:
- Data directory paths
- Stock lists (Dividend Kings, Aristocrats)
- Scoring weights and thresholds
- Data validation limits
- API settings
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Final, FrozenSet

# =============================================================================
# DATA DIRECTORY CONFIGURATION
# =============================================================================

def is_cloud_runtime() -> bool:
    """True on Streamlit Community Cloud and similar ephemeral hosts."""
    flag = os.environ.get("DIVIDENDSCOPE_CLOUD", "").strip().lower()
    if flag in ("1", "true", "yes"):
        return True
    if os.environ.get("STREAMLIT_RUNTIME_ENV", "").strip().lower() == "cloud":
        return True
    host = " ".join(
        (
            os.environ.get("HOSTNAME", ""),
            os.environ.get("STREAMLIT_SERVER_ADDRESS", ""),
            os.environ.get("STREAMLIT_SHARING_BASE_URL", ""),
        )
    ).lower()
    return "streamlit.app" in host


def _resolve_data_dir() -> Path:
    override = os.environ.get("DIVIDENDSCOPE_DATA_DIR")
    if override:
        return Path(override)
    if is_cloud_runtime():
        return Path(__file__).resolve().parent / "data"
    return Path.home() / ".dividendscope" / "data"


DATA_DIR: Final[Path] = _resolve_data_dir()

# Subdirectories — shared by all users (not per-account)
VECTORDB_DIR: Final[Path] = DATA_DIR / "vectordb"
SHARED_MARKET_DB_DIR: Final[Path] = VECTORDB_DIR
DOWNLOADS_DIR: Final[Path] = DATA_DIR / "downloads"
REPORTS_DIR: Final[Path] = Path("reports")


def _database_url_configured() -> bool:
    return bool(
        (os.environ.get("DATABASE_URL") or os.environ.get("DIVIDENDSCOPE_DATABASE_URL") or "").strip()
    )


# Ensure directories exist (local Chroma only when not using Postgres)
DATA_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
if not _database_url_configured():
    VECTORDB_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# DIVIDEND TIER DEFINITIONS
# =============================================================================

class DividendTier:
    """Dividend tier classification based on consecutive years of increases."""
    
    KING = 50        # 50+ years - Elite status
    ARISTOCRAT = 25  # 25+ years - S&P 500 Dividend Aristocrats
    ACHIEVER = 10    # 10+ years - Dividend Achievers
    CONTENDER = 5    # 5+ years - Dividend Contenders
    STARTER = 1      # 1+ years - Beginning dividend history


DIVIDEND_TIERS: Final[Dict[str, int]] = {
    "king": DividendTier.KING,
    "aristocrat": DividendTier.ARISTOCRAT,
    "achiever": DividendTier.ACHIEVER,
    "contender": DividendTier.CONTENDER,
}


# =============================================================================
# STOCK LISTS
# =============================================================================

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

# Tickers removed from lists and purged from the vector DB (no reliable Yahoo quotes)
DELISTED_SYMBOLS: Final[FrozenSet[str]] = frozenset({
    "WBA",   # Delisted / acquired (Walgreens Boots Alliance)
    "SJW",   # Acquired; no active Yahoo quote
    "LANC",  # Lancaster Colony — invalid history on Yahoo
    "BF.B",  # Brown-Forman Class B — use BF-B on Yahoo; kept out of DB
    "BF-B",
})

# Dividend Aristocrats for comparison (25+ years)
DIVIDEND_ARISTOCRATS: Final[List[str]] = [
    "ABBV", "ADM", "ADP", "AFL", "ALB", "AMCR", "AOS", "APD", "ATO", "BDX",
    "BEN", "BRO", "CAH", "CAT", "CB", "CHRW", "CINF", "CLX", "CTAS",
    "CVX", "ECL", "ED", "ESS", "EXPD", "FAST", "FDS", "GD", "IBM", "KMB",
    "LIN", "MCD", "MDT", "MKC", "NEE", "NUE", "O", "PEP", "ROP", "SPGI",
    "T", "TROW", "VFC", "WMT", "WST", "XOM",
]

# Combined list for full analysis (frozen for immutability)
ALL_DIVIDEND_STOCKS: Final[List[str]] = sorted(
    symbol for symbol in set(DIVIDEND_KINGS + DIVIDEND_ARISTOCRATS)
    if symbol not in DELISTED_SYMBOLS
)
DIVIDEND_SYMBOLS_SET: Final[FrozenSet[str]] = frozenset(ALL_DIVIDEND_STOCKS)


# =============================================================================
# SCORING CONFIGURATION
# =============================================================================

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


# =============================================================================
# DATA VALIDATION THRESHOLDS
# =============================================================================

# Maximum valid values (values above these are likely data errors)
MAX_DIVIDEND_YIELD_PCT: Final[float] = 15.0
MAX_PAYOUT_RATIO_PCT: Final[float] = 200.0
MAX_PE_RATIO: Final[float] = 500.0
MAX_DEBT_TO_EQUITY: Final[float] = 10.0

# Minimum valid values
MIN_MARKET_CAP: Final[float] = 1_000_000  # $1M minimum

# Dividend safety thresholds (payout ratio percentage)
PAYOUT_VERY_SAFE: Final[float] = 40.0
PAYOUT_SAFE: Final[float] = 60.0
PAYOUT_MODERATE: Final[float] = 75.0
PAYOUT_ELEVATED: Final[float] = 90.0
# Max payout ratio to store/display; values above are capped (avoids bad data showing 500%+)
MAX_PAYOUT_RATIO_PCT: Final[float] = 150.0


# =============================================================================
# API & RATE LIMITING
# =============================================================================

API_DELAY_SECONDS: Final[float] = 0.2
API_TIMEOUT_SECONDS: Final[int] = 30
MAX_RETRIES: Final[int] = 3


# =============================================================================
# DATA SOURCE ATTRIBUTION
# =============================================================================

DATA_SOURCES: Final[Dict[str, str]] = {
    "primary": "Market Data Aggregator",
    "fundamentals": "Public Financial Filings",
    "analyst": "Consensus Estimates",
    "historical": "Exchange Data",
}


# =============================================================================
# HISTORY LIMITS
# =============================================================================

MAX_HISTORY_YEARS: Final[int] = 10
DEFAULT_STALENESS_DAYS: Final[int] = 7

# Portfolio risk scan: only refreshed when the user clicks Reload / Refresh (not on a timer).
PORTFOLIO_RISK_REFRESH_SECONDS: Final[int] = 86400 * 365

# In-app assistant (sidebar chat). Optional HUGGINGFACE_API_KEY for LLM fallback.
CHATBOT_ENABLED_DEFAULT: Final[bool] = True
CHATBOT_HF_MODEL_DEFAULT: Final[str] = "facebook/blenderbot-400M-distill"
