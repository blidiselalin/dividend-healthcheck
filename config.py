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
from typing import Final

# =============================================================================
# DATA DIRECTORY CONFIGURATION
# =============================================================================


def _resolve_google_drive_data_dir() -> Path | None:
    """Resolve a Google Drive-backed data directory if configured."""
    explicit = os.environ.get("DIVIDENDSCOPE_GOOGLE_DRIVE_DATA_DIR")
    if explicit:
        return Path(explicit)

    use_drive = os.environ.get("DIVIDENDSCOPE_USE_GOOGLE_DRIVE", "").strip().lower()
    if use_drive not in {"1", "true", "yes", "on"}:
        return None

    # Common Google Drive Desktop location on macOS.
    cloud_storage = Path.home() / "Library" / "CloudStorage"
    if not cloud_storage.exists():
        return None

    drive_roots = sorted(cloud_storage.glob("GoogleDrive-*"))
    for root in drive_roots:
        # Drive folder naming can differ across locales/accounts.
        candidates = [
            root / "My Drive" / "DividendScopeData",
            root / "MyDrive" / "DividendScopeData",
            root / "Drive" / "DividendScopeData",
        ]
        for candidate in candidates:
            # Return first candidate path (created later by mkdir).
            if candidate.parent.exists():
                return candidate

    return None


def _resolve_data_dir() -> Path:
    """Resolve app data directory from env vars with sensible fallback."""
    explicit = os.environ.get("DIVIDENDSCOPE_DATA_DIR")
    if explicit:
        return Path(explicit)

    drive_path = _resolve_google_drive_data_dir()
    if drive_path is not None:
        return drive_path

    return Path.home() / ".dividendscope" / "data"


# Uses ~/.dividendscope/data by default, can be overridden with env vars.
DATA_DIR: Final[Path] = _resolve_data_dir()

# Subdirectories
VECTORDB_DIR: Final[Path] = DATA_DIR / "vectordb"
DOWNLOADS_DIR: Final[Path] = DATA_DIR / "downloads"
REPORTS_DIR: Final[Path] = Path("reports")

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
VECTORDB_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# DIVIDEND TIER DEFINITIONS
# =============================================================================


class DividendTier:
    """Dividend tier classification based on consecutive years of increases."""

    KING = 50  # 50+ years - Elite status
    ARISTOCRAT = 25  # 25+ years - S&P 500 Dividend Aristocrats
    ACHIEVER = 10  # 10+ years - Dividend Achievers
    CONTENDER = 5  # 5+ years - Dividend Contenders
    STARTER = 1  # 1+ years - Beginning dividend history


DIVIDEND_TIERS: Final[dict[str, int]] = {
    "king": DividendTier.KING,
    "aristocrat": DividendTier.ARISTOCRAT,
    "achiever": DividendTier.ACHIEVER,
    "contender": DividendTier.CONTENDER,
}


# =============================================================================
# STOCK LISTS
# =============================================================================

# Dividend stocks for analysis - including Kings (50+ years) and high-quality payers
DIVIDEND_KINGS: Final[list[str]] = [
    "ABBV",
    "ADM",
    "ADP",
    "AFG",
    "AMAT",
    "AMT",
    "ARCC",
    "ARE",
    "AWK",
    "BAC",
    "BBY",
    "BEN",
    "BMY",
    "BTI",
    "CMCSA",
    "CSCO",
    "DVN",
    "ESS",
    "HSY",
    "IBM",
    "INTU",
    "JNJ",
    "KO",
    "MDLZ",
    "MDT",
    "MMM",
    "MO",
    "NEE",
    "NKE",
    "NNN",
    "NSP",
    "O",
    "PEP",
    "PRU",
    "QCOM",
    "SBUX",
    "SWK",
    "SWKS",
    "T",
    "TROW",
    "UGI",
    "VSNT",
    "VZ",
    "WPC",
    "XOM",
    "ZTS",
]

# Dividend Aristocrats for comparison (25+ years)
DIVIDEND_ARISTOCRATS: Final[list[str]] = [
    "ABBV",
    "ADM",
    "ADP",
    "AFL",
    "ALB",
    "AMCR",
    "AOS",
    "APD",
    "ATO",
    "BDX",
    "BEN",
    "BF.B",
    "BRO",
    "CAH",
    "CAT",
    "CB",
    "CHRW",
    "CINF",
    "CLX",
    "CTAS",
    "CVX",
    "ECL",
    "ED",
    "ESS",
    "EXPD",
    "FAST",
    "FDS",
    "GD",
    "IBM",
    "KMB",
    "LIN",
    "MCD",
    "MDT",
    "MKC",
    "NEE",
    "NUE",
    "O",
    "PEP",
    "ROP",
    "SPGI",
    "T",
    "TROW",
    "VFC",
    "WBA",
    "WMT",
    "WST",
    "XOM",
]

# Combined list for full analysis (frozen for immutability)
ALL_DIVIDEND_STOCKS: Final[list[str]] = sorted(set(DIVIDEND_KINGS + DIVIDEND_ARISTOCRATS))
DIVIDEND_SYMBOLS_SET: Final[frozenset[str]] = frozenset(ALL_DIVIDEND_STOCKS)
DELISTED_SYMBOLS: Final[frozenset[str]] = frozenset()


# =============================================================================
# SCORING CONFIGURATION
# =============================================================================

# Scoring weights - total = 100 points (investor-focused)
SCORING_WEIGHTS: Final[dict[str, int]] = {
    "dividend_streak": 20,  # Years of consecutive increases (core criterion)
    "dividend_safety": 15,  # Payout ratio sustainability
    "dividend_yield": 15,  # Current income potential
    "dividend_growth": 15,  # CAGR of dividend increases
    "valuation": 10,  # P/E, forward P/E
    "financial_strength": 10,  # Debt levels, coverage ratios
    "profitability": 10,  # ROE, margins
    "size_stability": 5,  # Market cap (larger = more stable)
}

# Recommendation score thresholds
RECOMMENDATION_THRESHOLDS: Final[dict[str, int]] = {
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

# Dividend yield context thresholds (shared between UI display and scoring)
YIELD_OPTIMAL_MIN: Final[float] = 2.5   # lower bound of optimal income range
YIELD_OPTIMAL_MAX: Final[float] = 4.5   # upper bound of optimal income range
YIELD_CAUTION_MIN: Final[float] = 8.0   # above this → potential dividend trap

# Dividend growth context thresholds (shared between UI display and scoring)
GROWTH_STRONG_MIN: Final[float] = 6.0   # ≥ 6 % CAGR → strong growth
GROWTH_MODERATE_MIN: Final[float] = 3.0  # ≥ 3 % CAGR → moderate growth

# Payout watch threshold for UI context (complements PAYOUT_SAFE = 60)
PAYOUT_WATCH: Final[float] = 80.0       # 60 < payout ≤ 80 → watch zone


# =============================================================================
# API & RATE LIMITING
# =============================================================================

API_DELAY_SECONDS: Final[float] = 0.2
API_TIMEOUT_SECONDS: Final[int] = 30
MAX_RETRIES: Final[int] = 3


# =============================================================================
# DATA SOURCE ATTRIBUTION
# =============================================================================

DATA_SOURCES: Final[dict[str, str]] = {
    "primary": "Market Data Aggregator",
    "fundamentals": "Public Financial Filings",
    "analyst": "Consensus Estimates",
    "historical": "Exchange Data",
}


# =============================================================================
# HISTORY LIMITS
# =============================================================================
MAX_HISTORY_YEARS: Final[int] = 10


# =============================================================================
# RUNTIME ENVIRONMENT
# =============================================================================


def is_cloud_runtime() -> bool:
    """Return True when the app is running against a cloud Postgres database."""
    from db.connection import use_cloud_sql

    return use_cloud_sql()
DEFAULT_STALENESS_DAYS: Final[int] = 7
PORTFOLIO_RISK_REFRESH_SECONDS: Final[int] = 3600
MIN_YIELD_PRICE_POINTS: Final[int] = 252
MIN_YIELD_DIVIDEND_PAYMENTS: Final[int] = 4
PRICE_REFRESH_INTERVAL_SECONDS: Final[int] = 300

# Auto-trigger a thin-history backfill on portfolio load when holdings lack
# enough price/dividend data for yield charts (set DIVIDENDSCOPE_AUTO_BACKFILL_ON_LOAD=0 to disable).
AUTO_BACKFILL_ON_LOAD: Final[bool] = (
    os.environ.get("DIVIDENDSCOPE_AUTO_BACKFILL_ON_LOAD", "1").strip().lower()
    not in ("0", "false", "no")
)

# How many hours between automatic thin-history backfill runs in the scheduler
# daemon (DIVIDENDSCOPE_HISTORY_REFRESH_HOURS env var, default 6).
HISTORY_REFRESH_HOURS: Final[int] = max(
    1,
    int(os.environ.get("DIVIDENDSCOPE_HISTORY_REFRESH_HOURS", "6") or "6"),
)

# Age threshold (minutes) above which a cached price is shown as stale in the
# portfolio table until the background live-reload job updates it.
PRICE_STALE_MINUTES: Final[int] = 5
