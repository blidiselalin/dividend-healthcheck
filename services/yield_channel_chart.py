from __future__ import annotations

"""
Dividend Yield Channels Chart Service.

Implements the "Dividends Don't Lie" methodology by Geraldine Weiss (1988).
Uses historical dividend yield bands to identify buying/selling opportunities.

Key principles from top financial analysts:
- Geraldine Weiss: "A stock's dividend yield is the most honest indicator of value"
- Warren Buffett: "Price is what you pay, value is what you get"
- Benjamin Graham: "The margin of safety is always dependent on the price paid"

The yield channel strategy identifies:
- UNDERVALUED: When yield is higher than historical average (price is low)
- OVERVALUED: When yield is lower than historical average (price is high)
- FAIR VALUE: When yield is near historical average
"""

import logging
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
    DEPS_AVAILABLE = True
except ImportError:
    DEPS_AVAILABLE = False

# Try to import vector store for DB-first data
try:
    from data_ingestion.vector_store import VectorStore
    from data_ingestion.models import DividendRecord
    VECTOR_DB_AVAILABLE = True
except ImportError:
    VECTOR_DB_AVAILABLE = False


@dataclass
class YieldChannelData:
    """Container for yield channel analysis data."""
    symbol: str
    company_name: str
    current_yield: float
    current_price: float
    current_dividend: float
    
    # Statistical metrics (using Weiss methodology)
    avg_yield: float
    median_yield: float
    min_yield: float
    max_yield: float
    std_yield: float
    
    # Percentile-based zones (more robust than std)
    yield_10th: float  # Expensive zone boundary
    yield_25th: float  # Caution zone boundary
    yield_75th: float  # Value zone boundary  
    yield_90th: float  # Deep value zone boundary
    
    # Zone prices (what price gives you each yield level)
    deep_value_price: float    # At 90th percentile yield
    value_price: float         # At 75th percentile yield
    fair_value_price: float    # At median yield
    caution_price: float       # At 25th percentile yield
    expensive_price: float     # At 10th percentile yield
    
    # Current zone assessment
    zone: str  # "Deep Value", "Value", "Fair Value", "Caution", "Expensive"
    zone_score: float  # 0-100, higher = better value
    percentile: float  # Current yield percentile (higher = better value)
    
    # Historical data for charting
    dates: List[datetime]
    prices: List[float]
    yields: List[float]
    annual_dividends: List[float]
    
    # Analysis period
    years_analyzed: int
    data_points: int
    
    # Dividend growth metrics
    dividend_cagr_5y: Optional[float] = None
    dividend_cagr_10y: Optional[float] = None
    dividend_streak: Optional[int] = None


def _ordered_percentiles(stats: Dict[str, float]) -> Dict[str, float]:
    """Ensure yield percentiles are monotonic (avoids crossed band lines)."""
    keys = ("p10", "p25", "median", "p75", "p90")
    values = [float(stats[k]) for k in keys]
    values.sort()
    return {
        "p10": values[0],
        "p25": values[1],
        "median": values[2],
        "p75": values[3],
        "p90": values[4],
        "mean": float(stats["mean"]),
        "std": float(stats["std"]),
        "min": float(stats["min"]),
        "max": float(stats["max"]),
    }


def validate_yield_channel_data(data: YieldChannelData) -> Optional[YieldChannelData]:
    """
    Sanitize series and price targets before charting.

    Returns None if the payload cannot be shown safely.
    """
    if data is None:
        return None

    n = len(data.dates)
    min_points = 13
    if n < min_points or len(data.prices) != n or len(data.yields) != n:
        return None

    pairs = sorted(
        zip(data.dates, data.prices, data.yields),
        key=lambda row: row[0],
    )
    dates, prices, yields = [], [], []
    for dt, price, yld in pairs:
        if price is None or yld is None:
            continue
        try:
            price_f = float(price)
            yld_f = float(yld)
        except (TypeError, ValueError):
            continue
        if price_f != price_f or yld_f != yld_f:  # NaN check without numpy
            continue
        if price_f <= 0 or yld_f < 0.01 or yld_f > 25:
            continue
        dates.append(dt)
        prices.append(price_f)
        yields.append(yld_f)

    if len(dates) < min_points:
        return None

    current_price = float(data.current_price)
    current_div = float(data.current_dividend)
    current_yield = float(data.current_yield)
    if current_price <= 0 or current_div <= 0 or current_yield <= 0:
        return None

    stats = _ordered_percentiles(
        {
            "p10": data.yield_10th,
            "p25": data.yield_25th,
            "median": data.median_yield,
            "p75": data.yield_75th,
            "p90": data.yield_90th,
            "mean": data.avg_yield,
            "std": data.std_yield,
            "min": data.min_yield,
            "max": data.max_yield,
        }
    )

    def _target(div: float, yld: float) -> float:
        return div / (yld / 100.0) if yld > 0 else 0.0

    targets = {
        "expensive": _target(current_div, stats["p10"]),
        "caution": _target(current_div, stats["p25"]),
        "fair_value": _target(current_div, stats["median"]),
        "value": _target(current_div, stats["p75"]),
        "deep_value": _target(current_div, stats["p90"]),
    }

    lo = min(prices) * 0.65
    hi = max(prices) * 1.35
    for key, val in list(targets.items()):
        if val != val or val <= 0:
            targets[key] = current_price
        else:
            targets[key] = float(max(lo, min(val, hi * 2)))

    # Deep value (lowest $) → expensive (highest $)
    targets = dict(sorted(targets.items(), key=lambda item: item[1]))

    return YieldChannelData(
        symbol=data.symbol,
        company_name=data.company_name,
        current_yield=round(current_yield, 2),
        current_price=round(current_price, 2),
        current_dividend=round(current_div, 2),
        avg_yield=round(stats["mean"], 2),
        median_yield=round(stats["median"], 2),
        min_yield=round(stats["min"], 2),
        max_yield=round(stats["max"], 2),
        std_yield=round(stats["std"], 2),
        yield_10th=round(stats["p10"], 2),
        yield_25th=round(stats["p25"], 2),
        yield_75th=round(stats["p75"], 2),
        yield_90th=round(stats["p90"], 2),
        deep_value_price=round(targets["deep_value"], 2),
        value_price=round(targets["value"], 2),
        fair_value_price=round(targets["fair_value"], 2),
        caution_price=round(targets["caution"], 2),
        expensive_price=round(targets["expensive"], 2),
        zone=data.zone,
        zone_score=data.zone_score,
        percentile=data.percentile,
        dates=dates,
        prices=prices,
        yields=yields,
        annual_dividends=data.annual_dividends[-len(dates) :]
        if len(data.annual_dividends) >= len(dates)
        else [current_div] * len(dates),
        years_analyzed=data.years_analyzed,
        data_points=len(dates),
        dividend_cagr_5y=data.dividend_cagr_5y,
        dividend_cagr_10y=data.dividend_cagr_10y,
        dividend_streak=data.dividend_streak,
    )


class YieldChannelService:
    """
    Service for calculating and charting dividend yield channels.
    
    Implements the "Dividends Don't Lie" strategy:
    1. Buy when yield is ABOVE average (price is depressed)
    2. Sell/avoid when yield is BELOW average (price is elevated)
    3. Use historical yield bands to set price targets
    
    Data sources (in priority order):
    1. Vector DB (if available and has historical data)
    2. yfinance API (fallback)
    """
    
    # Zone definitions following Weiss methodology
    ZONES = {
        "Deep Value": {"min_pct": 90, "max_pct": 100, "color": "#1a5f1a", "emoji": "🟢💎"},
        "Value": {"min_pct": 75, "max_pct": 90, "color": "#4caf50", "emoji": "🟢"},
        "Fair Value": {"min_pct": 25, "max_pct": 75, "color": "#ffc107", "emoji": "🟡"},
        "Caution": {"min_pct": 10, "max_pct": 25, "color": "#ff9800", "emoji": "🟠"},
        "Expensive": {"min_pct": 0, "max_pct": 10, "color": "#f44336", "emoji": "🔴"},
    }
    
    def __init__(self, vector_store: Optional[Any] = None):
        """Initialize with optional vector store for DB-first data."""
        self._vector_store = vector_store
        
        # Shared market library (Postgres or local Chroma)
        if self._vector_store is None:
            try:
                from services.shared_market_db import get_shared_vector_store

                self._vector_store = get_shared_vector_store()
            except Exception as e:
                if VECTOR_DB_AVAILABLE:
                    try:
                        self._vector_store = VectorStore()
                    except Exception as inner:
                        logger.debug("Could not initialize VectorStore: %s", inner)
                else:
                    logger.debug("Shared market library unavailable: %s", e)
    
    def fetch_yield_channel_data(
        self,
        symbol: str, 
        years: int = 10,
        use_db: bool = True,
        document: Any = None,
        *,
        min_price_rows: int = 120,
        min_yield_rows: int = 60,
    ) -> Optional[YieldChannelData]:
        """
        Fetch historical data and calculate yield channel metrics.
        
        Implements the Geraldine Weiss methodology:
        - Uses percentiles instead of standard deviations (more robust)
        - Accounts for dividend growth over time
        - Provides actionable buy/sell zones
        
        Args:
            symbol: Stock ticker symbol
            years: Number of years of historical data (default 10 per Weiss)
            use_db: Try to use vector DB data first
            document: Optional pre-loaded library document (skips lookup)
            min_price_rows: Minimum daily price rows required
            min_yield_rows: Minimum yield sample points after TTM alignment
            
        Returns:
            YieldChannelData or None if data unavailable
        """
        if not DEPS_AVAILABLE:
            return None
        
        # Try vector DB first for historical dividend data
        db_dividend_history = None
        db_streak = None
        db_doc = document

        if db_doc is None and use_db and self._vector_store:
            try:
                db_doc = self._vector_store.get_by_symbol(symbol)
            except Exception as e:
                logger.debug("Vector DB lookup failed for %s: %s", symbol, e)

        if db_doc and db_doc.dividend_history:
            db_dividend_history = db_doc.dividend_history
            db_streak = db_doc.dividend_streak_years
            logger.debug("%s: Found %d dividends in DB", symbol, len(db_dividend_history))

        try:
            ticker = yf.Ticker(symbol)

            # Get company name
            company_name = symbol
            if db_doc and getattr(db_doc, "name", None):
                company_name = db_doc.name
            else:
                try:
                    info = ticker.info
                    company_name = info.get("shortName") or info.get("longName") or symbol
                except Exception:
                    pass

            from utils.yfinance_history import (
                compute_ttm_from_payment_series,
                dividend_series_from_document,
                dividend_series_from_records,
                fetch_dividend_series,
                fetch_price_history_with_fallback,
                merge_dividend_series,
                unique_price_dates,
            )

            min_price_rows = max(52, int(min_price_rows))
            min_yield_rows = max(13, int(min_yield_rows))
            price_count = unique_price_dates(db_doc) if db_doc else 0
            div_count = len(db_dividend_history or [])
            prefer_library = price_count >= 52 and div_count >= 2
            library_min_rows = min(min_price_rows, price_count) if prefer_library else min_price_rows

            hist, price_source = fetch_price_history_with_fallback(
                symbol,
                years=years,
                document=db_doc,
                min_rows=library_min_rows,
                prefer_library=prefer_library,
            )
            prepared = self._prepare_history_frame(hist)
            if len(prepared) < min(min_price_rows, 52) and prefer_library:
                hist, price_source = fetch_price_history_with_fallback(
                    symbol,
                    years=years,
                    document=db_doc,
                    min_rows=library_min_rows,
                    prefer_library=False,
                )
                prepared = self._prepare_history_frame(hist)
            if prepared.empty or len(prepared) < min(min_price_rows, 52):
                logger.debug(
                    "%s: insufficient price history (source=%s, rows=%d)",
                    symbol,
                    price_source,
                    len(prepared),
                )
                return None
            if price_source == "analysed_library":
                logger.debug("%s: yield channel using analysed-library prices", symbol)

            hist = prepared

            library_divs = dividend_series_from_records(db_dividend_history or [])
            if library_divs.empty and db_doc is not None:
                library_divs = dividend_series_from_document(db_doc, years=years)
            if len(library_divs) >= 4:
                payment_series = library_divs
            else:
                payment_series = merge_dividend_series(
                    library_divs,
                    fetch_dividend_series(symbol),
                )

            if payment_series.empty:
                logger.debug("%s: no dividend payments in library or yfinance", symbol)
                return None

            hist = compute_ttm_from_payment_series(
                prepared,
                payment_series,
                min_rows=max(13, min(min_yield_rows, len(prepared) // 3)),
            )
            if hist is None:
                aligned = self._ensure_dividends_on_history(
                    prepared,
                    symbol,
                    db_dividend_history,
                    db_doc=db_doc,
                )
                if float(aligned["Dividends"].sum()) == 0:
                    logger.debug("%s: no dividend payments on price history", symbol)
                    return None
                hist = self._calculate_ttm_dividend(aligned)
                effective_min = max(13, min(min_yield_rows, len(aligned) // 3))
                if hist is None or len(hist) < effective_min:
                    logger.debug("%s: could not compute trailing dividend", symbol)
                    return None

            hist["Yield"] = (hist["Div_TTM"] / hist["Close"]) * 100
            hist = hist[(hist["Yield"] >= 0.01) & (hist["Yield"] < 25)]
            effective_min_yield = max(13, min(min_yield_rows, len(hist)))
            if len(hist) < effective_min_yield:
                logger.debug(
                    "%s: insufficient yield points after filter (%d)",
                    symbol,
                    len(hist),
                )
                return None

            hist = self._downsample_for_display(hist)
            min_display_rows = max(13, min(min_yield_rows // 2, len(hist)))
            if len(hist) < min_display_rows:
                return None

            from utils.yield_channel_history import years_covered_by_frame

            years_analyzed = min(years, years_covered_by_frame(hist))

            # Statistical analysis using percentiles (Weiss methodology)
            yields = hist["Yield"].dropna()
            stats = _ordered_percentiles(self._calculate_yield_statistics(yields))
            
            # Current values
            current_price = float(hist["Close"].iloc[-1])
            current_div = float(hist["Div_TTM"].iloc[-1])
            current_yield = float(hist["Yield"].iloc[-1])
            
            # Calculate percentile of current yield
            percentile = float((yields < current_yield).sum() / len(yields) * 100)
            
            # Determine zone based on percentile
            zone = self._determine_zone(percentile)
            zone_score = self._calculate_zone_score(percentile, zone)
            
            # Calculate price targets at different yield levels
            price_targets = self._calculate_price_targets(current_div, stats)

            # Calculate dividend growth metrics
            dividend_growth = self._calculate_dividend_growth(hist)

            payload = YieldChannelData(
                symbol=symbol,
                company_name=company_name,
                current_yield=round(current_yield, 2),
                current_price=round(current_price, 2),
                current_dividend=round(current_div, 2),
                avg_yield=round(stats["mean"], 2),
                median_yield=round(stats["median"], 2),
                min_yield=round(stats["min"], 2),
                max_yield=round(stats["max"], 2),
                std_yield=round(stats["std"], 2),
                yield_10th=round(stats["p10"], 2),
                yield_25th=round(stats["p25"], 2),
                yield_75th=round(stats["p75"], 2),
                yield_90th=round(stats["p90"], 2),
                deep_value_price=round(price_targets["deep_value"], 2),
                value_price=round(price_targets["value"], 2),
                fair_value_price=round(price_targets["fair_value"], 2),
                caution_price=round(price_targets["caution"], 2),
                expensive_price=round(price_targets["expensive"], 2),
                zone=zone,
                zone_score=round(zone_score, 1),
                percentile=round(percentile, 1),
                dates=hist.index.tolist(),
                prices=hist["Close"].tolist(),
                yields=hist["Yield"].tolist(),
                annual_dividends=hist["Div_TTM"].tolist(),
                years_analyzed=years_analyzed,
                data_points=len(hist),
                dividend_cagr_5y=dividend_growth.get("cagr_5y"),
                dividend_cagr_10y=dividend_growth.get("cagr_10y"),
                dividend_streak=db_streak,
            )
            return validate_yield_channel_data(payload)

        except Exception as e:
            logger.error(f"Error fetching yield channel data for {symbol}: {e}")
            return None

    @staticmethod
    def _prepare_history_frame(hist: pd.DataFrame) -> pd.DataFrame:
        """Sort, dedupe, and normalize OHLCV before yield math."""
        from utils.yfinance_history import densify_price_history

        frame = hist.copy()
        frame = frame.sort_index()
        frame = frame[~frame.index.duplicated(keep="last")]
        if "Adj Close" in frame.columns:
            frame["Close"] = frame["Adj Close"]
        frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
        frame = frame.dropna(subset=["Close"])
        frame = frame[frame["Close"] > 0]
        if "Dividends" not in frame.columns:
            frame["Dividends"] = 0.0
        frame["Dividends"] = pd.to_numeric(frame["Dividends"], errors="coerce").fillna(0.0)
        frame = densify_price_history(frame)
        return frame

    @staticmethod
    def _downsample_for_display(hist: pd.DataFrame) -> pd.DataFrame:
        """Weekly points for a readable 10Y chart (less noise than daily)."""
        if len(hist) <= 320:
            return hist
        agg: Dict[str, str] = {
            "Close": "last",
            "Div_TTM": "last",
            "Yield": "last",
        }
        if "Dividends" in hist.columns:
            agg["Dividends"] = "sum"
        weekly = hist.resample("W-FRI").agg(agg)
        return weekly.dropna(subset=["Close", "Yield", "Div_TTM"])

    @staticmethod
    def _dividend_series_from_records(db_dividends: List) -> pd.Series:
        """Build a payment series from analysed-library dividend records."""
        from utils.yfinance_history import dividend_series_from_records

        return dividend_series_from_records(db_dividends)

    @staticmethod
    def _dividend_payment_count(frame: pd.DataFrame) -> int:
        if frame is None or frame.empty or "Dividends" not in frame.columns:
            return 0
        return int((pd.to_numeric(frame["Dividends"], errors="coerce").fillna(0) > 0).sum())

    @staticmethod
    def _dividend_series_from_document(doc: Any, *, years: int = 10) -> pd.Series:
        """Use stored dividend_history or estimate quarterly payouts from yield metadata."""
        from utils.yfinance_history import dividend_series_from_document

        return dividend_series_from_document(doc, years=years)

    def _ensure_dividends_on_history(
        self,
        hist: pd.DataFrame,
        symbol: str,
        db_dividend_history: Optional[List],
        *,
        db_doc: Any = None,
    ) -> pd.DataFrame:
        """Merge library-first dividends onto the price index (rolling-TTM fallback)."""
        from utils.yfinance_history import align_dividends_to_price_index, fetch_dividend_series

        frame = self._prepare_history_frame(hist)
        min_payments = 4

        if db_dividend_history:
            db_series = self._dividend_series_from_records(db_dividend_history)
            if not db_series.empty:
                frame = align_dividends_to_price_index(frame, db_series)

        if self._dividend_payment_count(frame) < min_payments and db_doc is not None:
            doc_series = self._dividend_series_from_document(db_doc)
            if not doc_series.empty:
                frame = align_dividends_to_price_index(frame, doc_series)

        if self._dividend_payment_count(frame) < min_payments:
            yf_series = fetch_dividend_series(symbol)
            if not yf_series.empty:
                frame = align_dividends_to_price_index(frame, yf_series)

        return frame

    def _integrate_db_dividends(self, hist: pd.DataFrame, db_dividends: List) -> pd.DataFrame:
        """Integrate vector DB dividend data into price history (legacy entry point)."""
        series = self._dividend_series_from_records(db_dividends)
        if series.empty:
            return hist
        from utils.yfinance_history import align_dividends_to_price_index

        return align_dividends_to_price_index(hist, series)
    
    def _calculate_ttm_dividend(self, hist: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Calculate trailing 12-month dividend at each point."""
        try:
            if "Dividends" not in hist.columns:
                return None
            
            dividends = hist["Dividends"]
            if dividends.sum() == 0:
                return None
            
            # Rolling 252 trading days (~1 year); lower min_periods for sparse payout rows
            hist["Div_TTM"] = dividends.rolling(window=252, min_periods=42).sum()
            
            # Fill gaps
            hist["Div_TTM"] = hist["Div_TTM"].ffill().bfill()
            
            # Replace zeros
            hist.loc[hist["Div_TTM"] == 0, "Div_TTM"] = np.nan
            hist["Div_TTM"] = hist["Div_TTM"].ffill()
            
            # Drop invalid rows
            hist = hist.dropna(subset=["Div_TTM", "Close"])
            
            return hist if len(hist) >= 60 else None
        except Exception:
            return None
    
    def _calculate_yield_statistics(self, yields: pd.Series) -> Dict[str, float]:
        """Calculate comprehensive yield statistics."""
        return {
            "mean": float(yields.mean()),
            "median": float(yields.median()),
            "std": float(yields.std()),
            "min": float(yields.min()),
            "max": float(yields.max()),
            "p10": float(yields.quantile(0.10)),
            "p25": float(yields.quantile(0.25)),
            "p75": float(yields.quantile(0.75)),
            "p90": float(yields.quantile(0.90)),
        }
    
    def _determine_zone(self, percentile: float) -> str:
        """Determine value zone based on yield percentile."""
        for zone_name, zone_def in self.ZONES.items():
            if zone_def["min_pct"] <= percentile <= zone_def["max_pct"]:
                return zone_name
        return "Fair Value"
    
    def _calculate_zone_score(self, percentile: float, zone: str) -> float:
        """Calculate value score (0-100, higher = better value)."""
        # Percentile directly maps to score (higher yield = higher score)
        return percentile
    
    def _calculate_price_targets(
        self, current_dividend: float, stats: Dict[str, float]
    ) -> Dict[str, float]:
        """Calculate price targets at different yield levels."""
        def price_at_yield(div: float, yld: float) -> float:
            return div / (yld / 100) if yld > 0 else 0
        
        return {
            "deep_value": price_at_yield(current_dividend, stats["p90"]),
            "value": price_at_yield(current_dividend, stats["p75"]),
            "fair_value": price_at_yield(current_dividend, stats["median"]),
            "caution": price_at_yield(current_dividend, stats["p25"]),
            "expensive": price_at_yield(current_dividend, stats["p10"]),
        }
    
    def _calculate_dividend_growth(self, hist: pd.DataFrame) -> Dict[str, Optional[float]]:
        """Calculate dividend CAGR."""
        result: Dict[str, Optional[float]] = {"cagr_5y": None, "cagr_10y": None}
        
        try:
            if "Div_TTM" not in hist.columns:
                return result
            
            # Get annual values
            try:
                annual = hist["Div_TTM"].resample("YE").last().dropna()
            except ValueError:
                annual = hist["Div_TTM"].resample("Y").last().dropna()
            if len(annual) < 2:
                return result
            
            # Current year (use most recent)
            current = float(annual.iloc[-1])
            
            # 5-year CAGR
            if len(annual) >= 6:
                start_5 = float(annual.iloc[-6])
                if start_5 > 0 and current > 0:
                    result["cagr_5y"] = round(((current / start_5) ** (1/5) - 1) * 100, 1)
            
            # 10-year CAGR
            if len(annual) >= 11:
                start_10 = float(annual.iloc[-11])
                if start_10 > 0 and current > 0:
                    result["cagr_10y"] = round(((current / start_10) ** (1/10) - 1) * 100, 1)
            
        except Exception:
            pass
        
        return result
    
    def create_yield_channel_chart(
        self,
        data: YieldChannelData,
        height: int = 520,
        show_annotations: bool = False,
    ) -> Optional[Any]:
        """
        Create professional Plotly chart showing yield channels.
        
        Design follows best practices from financial publications:
        - Clean, institutional-grade styling
        - Clear zone demarcations with gradient fills
        - Actionable price targets
        - Historical context with dividend growth
        
        Args:
            data: YieldChannelData from fetch_yield_channel_data
            height: Chart height in pixels
            show_annotations: Show price target annotations
            
        Returns:
            Plotly figure object or None
        """
        if not PLOTLY_AVAILABLE or data is None:
            return None

        clean = validate_yield_channel_data(data)
        if clean is None:
            return None
        data = clean

        dates = list(data.dates)
        prices = list(data.prices)
        yields = list(data.yields)
        zone_color = self.ZONES.get(data.zone, {}).get("color", "#0f766e")

        fig = make_subplots(
            rows=2,
            cols=1,
            row_heights=[0.58, 0.42],
            shared_xaxes=True,
            vertical_spacing=0.06,
            subplot_titles=(
                f"{data.symbol} price — green to red = cheaper to pricier (today’s ${data.current_dividend:.2f} dividend)",
                f"Trailing yield — dashed lines = {data.years_analyzed}Y percentiles",
            ),
        )

        for y0, y1, fill in (
            (data.deep_value_price, data.value_price, "rgba(22, 163, 74, 0.10)"),
            (data.value_price, data.fair_value_price, "rgba(234, 179, 8, 0.10)"),
            (data.fair_value_price, data.caution_price, "rgba(249, 115, 22, 0.08)"),
            (data.caution_price, data.expensive_price, "rgba(239, 68, 68, 0.08)"),
        ):
            if y1 > y0:
                fig.add_hrect(y0=y0, y1=y1, fillcolor=fill, line_width=0, row=1, col=1)

        x_band = [dates[0], dates[-1]]
        for price_level, color, dash in (
            (data.expensive_price, "#dc2626", "dot"),
            (data.caution_price, "#ea580c", "dash"),
            (data.fair_value_price, "#64748b", "solid"),
            (data.value_price, "#16a34a", "dash"),
            (data.deep_value_price, "#14532d", "dot"),
        ):
            fig.add_trace(
                go.Scatter(
                    x=x_band,
                    y=[price_level, price_level],
                    mode="lines",
                    line=dict(color=color, width=1, dash=dash),
                    showlegend=False,
                    hoverinfo="skip",
                ),
                row=1,
                col=1,
            )

        fig.add_trace(
            go.Scatter(
                x=dates,
                y=prices,
                mode="lines",
                name="Share price",
                line=dict(color="#0f766e", width=2.5),
                hovertemplate="%{x|%b %Y}<br>Price $%{y:.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=[dates[-1]],
                y=[data.current_price],
                mode="markers",
                name=f"Now ${data.current_price:.2f}",
                marker=dict(size=10, color=zone_color, line=dict(width=2, color="white")),
                hovertemplate=f"Current ${data.current_price:.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )

        price_lo = min(min(prices), data.deep_value_price) * 0.92
        price_hi = max(max(prices), data.expensive_price) * 1.08
        fig.update_yaxes(range=[price_lo, price_hi], row=1, col=1)

        fig.add_trace(
            go.Scatter(
                x=dates,
                y=yields,
                mode="lines",
                name="Trailing yield",
                line=dict(color="#c2410c", width=2),
                hovertemplate="%{x|%b %Y}<br>Yield %{y:.2f}%<extra></extra>",
            ),
            row=2,
            col=1,
        )

        for y_level, color, dash in (
            (data.yield_90th, "#14532d", "dot"),
            (data.yield_75th, "#16a34a", "dash"),
            (data.median_yield, "#64748b", "solid"),
            (data.yield_25th, "#ea580c", "dash"),
            (data.yield_10th, "#dc2626", "dot"),
        ):
            fig.add_trace(
                go.Scatter(
                    x=x_band,
                    y=[y_level, y_level],
                    mode="lines",
                    line=dict(color=color, width=1, dash=dash),
                    showlegend=False,
                    hoverinfo="skip",
                ),
                row=2,
                col=1,
            )

        fig.add_trace(
            go.Scatter(
                x=[dates[-1]],
                y=[data.current_yield],
                mode="markers",
                marker=dict(size=9, color=zone_color, symbol="diamond"),
                showlegend=False,
                hovertemplate=f"Current {data.current_yield:.2f}%<extra></extra>",
            ),
            row=2,
            col=1,
        )

        y_lo = max(0, min(yields) * 0.85)
        y_hi = max(yields) * 1.12
        fig.update_yaxes(range=[y_lo, y_hi], row=2, col=1)

        from utils.chart_theme import PALETTE, style_figure, style_subplot_titles

        style_subplot_titles(fig, size=12)

        fig.update_yaxes(title_text="Price", tickprefix="$", row=1, col=1)
        fig.update_yaxes(title_text="Yield", ticksuffix="%", row=2, col=1)

        style_figure(
            fig,
            height=height,
            legend=True,
            horizontal_legend=True,
            margin=dict(l=52, r=20, t=64, b=40),
        )

        if show_annotations:
            fig.add_annotation(
                x=dates[-1],
                y=data.current_price,
                text=data.zone,
                showarrow=False,
                yshift=12,
                font=dict(size=11, color=zone_color),
                bgcolor="white",
                bordercolor=zone_color,
                borderwidth=1,
            )

        # Zone guide (right margin text via annotation)
        fig.add_annotation(
            xref="paper",
            yref="paper",
            x=1.0,
            y=1.12,
            xanchor="right",
            showarrow=False,
            text=(
                f"<span style='color:{PALETTE['muted']};font-size:10px'>"
                f"Green=cheaper · Red=pricier · vs ${data.current_dividend:.2f}/yr div</span>"
            ),
        )

        return fig

    @staticmethod
    def get_zone_info(zone: str) -> Dict[str, Any]:
        """Get zone information including color and emoji."""
        return YieldChannelService.ZONES.get(zone, {
            "color": "#9e9e9e",
            "emoji": "⚪",
            "min_pct": 0,
            "max_pct": 100,
        })
    
    @staticmethod
    def get_zone_color(zone: str) -> str:
        """Get color code for zone."""
        return YieldChannelService.ZONES.get(zone, {}).get("color", "#9e9e9e")
    
    @staticmethod
    def get_zone_emoji(zone: str) -> str:
        """Get emoji for zone."""
        return YieldChannelService.ZONES.get(zone, {}).get("emoji", "⚪")
    
    def format_analysis_summary(self, data: YieldChannelData) -> Dict[str, Any]:
        """
        Generate comprehensive analysis summary.
        
        Follows the Weiss methodology with actionable insights:
        - Clear buy/sell/hold recommendation
        - Price targets with rationale
        - Dividend growth context
        - Risk assessment
        """
        zone_info = self.get_zone_info(data.zone)
        
        # Calculate gaps to price targets
        to_fair = ((data.fair_value_price / data.current_price) - 1) * 100
        to_value = ((data.value_price / data.current_price) - 1) * 100
        to_expensive = ((data.expensive_price / data.current_price) - 1) * 100
        
        # Determine action based on Weiss principles
        if data.zone == "Deep Value":
            action = "Strong Buy"
            action_detail = (
                f"Yield ({data.current_yield:.1f}%) is in the top 10% of historical range. "
                f"Price ${data.current_price:.2f} offers exceptional value."
            )
            action_color = "#1b5e20"
        elif data.zone == "Value":
            action = "Buy"
            action_detail = (
                f"Yield ({data.current_yield:.1f}%) above historical median. "
                f"Good entry point for long-term dividend investors."
            )
            action_color = "#4caf50"
        elif data.zone == "Fair Value":
            action = "Hold / Accumulate"
            action_detail = (
                f"Yield ({data.current_yield:.1f}%) near {data.years_analyzed}Y median ({data.median_yield:.1f}%). "
                f"Fair price for dollar-cost averaging."
            )
            action_color = "#ff9800"
        elif data.zone == "Caution":
            action = "Wait"
            action_detail = (
                f"Yield ({data.current_yield:.1f}%) below average suggests price is elevated. "
                f"Consider waiting for better entry."
            )
            action_color = "#f57c00"
        else:  # Expensive
            action = "Avoid / Trim"
            action_detail = (
                f"Yield ({data.current_yield:.1f}%) in bottom 10% historically. "
                f"Price may be overextended. Consider taking profits."
            )
            action_color = "#d32f2f"
        
        # Dividend growth context
        growth_status = "Unknown"
        if data.dividend_cagr_5y is not None:
            if data.dividend_cagr_5y >= 7:
                growth_status = "Strong Growth"
            elif data.dividend_cagr_5y >= 4:
                growth_status = "Steady Growth"
            elif data.dividend_cagr_5y >= 0:
                growth_status = "Slow Growth"
            else:
                growth_status = "Declining"
        
        return {
            "zone": data.zone,
            "zone_emoji": zone_info.get("emoji", "⚪"),
            "zone_color": zone_info.get("color", "#9e9e9e"),
            "zone_score": data.zone_score,
            "percentile": data.percentile,
            
            "current_yield": data.current_yield,
            "median_yield": data.median_yield,
            "yield_vs_median": data.current_yield - data.median_yield,
            
            "current_price": data.current_price,
            "fair_value_price": data.fair_value_price,
            "value_price": data.value_price,
            "expensive_price": data.expensive_price,
            "deep_value_price": data.deep_value_price,
            
            "gap_to_fair_pct": to_fair,
            "gap_to_value_pct": to_value,
            "gap_to_expensive_pct": to_expensive,
            
            "action": action,
            "action_detail": action_detail,
            "action_color": action_color,
            
            "dividend_cagr_5y": data.dividend_cagr_5y,
            "dividend_cagr_10y": data.dividend_cagr_10y,
            "dividend_streak": data.dividend_streak,
            "growth_status": growth_status,
            
            "years_analyzed": data.years_analyzed,
            "data_points": data.data_points,
            "current_dividend": data.current_dividend,
        }
    
    def get_weiss_interpretation(self, data: YieldChannelData) -> str:
        """
        Get interpretation following Geraldine Weiss methodology.
        
        From "Dividends Don't Lie" (1988):
        - "When a stock's yield is high relative to its historical norm, 
           the stock is undervalued."
        - "When a stock's yield is low, the stock is overvalued."
        """
        pct = data.percentile
        
        if pct >= 90:
            return (
                f"📈 **Exceptional Value** • {data.symbol}'s current yield of {data.current_yield:.2f}% "
                f"is higher than {pct:.0f}% of the past {data.years_analyzed} years. "
                f"Per Weiss methodology, this indicates significant undervaluation. "
                f"The market is offering this dividend stream at a steep discount."
            )
        elif pct >= 75:
            return (
                f"✅ **Good Value** • At {data.current_yield:.2f}%, the yield is above the 75th percentile. "
                f"This is a favorable entry point for dividend-focused investors. "
                f"The price offers an above-average income return."
            )
        elif pct >= 50:
            return (
                f"🟡 **Fair Value** • The current {data.current_yield:.2f}% yield is near the historical median. "
                f"Neither significantly undervalued nor overvalued. "
                f"Suitable for systematic investment or holding existing positions."
            )
        elif pct >= 25:
            return (
                f"⚠️ **Below Average Value** • At {data.current_yield:.2f}%, yield is lower than {100-pct:.0f}% "
                f"of historical observations. Price may have outrun fundamentals. "
                f"Consider waiting for a better entry point."
            )
        else:
            return (
                f"🛑 **Overvalued** • Current yield of {data.current_yield:.2f}% is in the bottom {pct:.0f}% "
                f"historically. The stock is priced for perfection. "
                f"Per Weiss: when yield is extremely low, the risk/reward is unfavorable."
            )


def _default_yield_channel_service() -> "YieldChannelService":
    try:
        from services.shared_market_db import get_shared_vector_store

        return YieldChannelService(vector_store=get_shared_vector_store())
    except Exception:
        return YieldChannelService()


def is_available() -> bool:
    """Check if yield channel charting is available."""
    return PLOTLY_AVAILABLE and DEPS_AVAILABLE
