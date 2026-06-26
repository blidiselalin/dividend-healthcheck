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

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, ClassVar, cast

logger = logging.getLogger(__name__)

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf

    DEPS_AVAILABLE = True
except ImportError:
    DEPS_AVAILABLE = False

# Try to import vector store for DB-first data
try:
    from data_ingestion.vector_store import VectorStore

    VECTOR_DB_AVAILABLE = True
except ImportError:
    VECTOR_DB_AVAILABLE = False


# For backward compatibility with tests
def _ordered_percentiles(stats: dict[str, Any]) -> dict[str, Any]:
    vals = sorted([stats["p10"], stats["p25"], stats["median"], stats["p75"], stats["p90"]])
    res = dict(stats)
    res["p10"] = vals[0]
    res["p25"] = vals[1]
    res["median"] = vals[2]
    res["p75"] = vals[3]
    res["p90"] = vals[4]
    return res


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
    deep_value_price: float  # At 90th percentile yield
    value_price: float  # At 75th percentile yield
    fair_value_price: float  # At median yield
    caution_price: float  # At 25th percentile yield
    expensive_price: float  # At 10th percentile yield

    # Current zone assessment
    zone: str  # "Deep Value", "Value", "Fair Value", "Caution", "Expensive"
    zone_score: float  # 0-100, higher = better value
    percentile: float  # Current yield percentile (higher = better value)

    # Historical data for charting
    dates: list[datetime]
    prices: list[float]
    yields: list[float]
    annual_dividends: list[float]

    # Analysis period
    years_analyzed: int
    data_points: int

    # Dividend growth metrics
    dividend_cagr_5y: float | None = None
    dividend_cagr_10y: float | None = None
    dividend_streak: int | None = None


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
    ZONES: ClassVar[dict[str, Any]] = {
        "Deep Value": {
            "min_pct": 90,
            "max_pct": 100,
            "color": "#34d399",
            "emoji": "🟢💎",
        },
        "Value": {"min_pct": 75, "max_pct": 90, "color": "#4ade80", "emoji": "🟢"},
        "Fair Value": {"min_pct": 25, "max_pct": 75, "color": "#fbbf24", "emoji": "🟡"},
        "Caution": {"min_pct": 10, "max_pct": 25, "color": "#fb923c", "emoji": "🟠"},
        "Expensive": {"min_pct": 0, "max_pct": 10, "color": "#f87171", "emoji": "🔴"},
    }

    def __init__(self, vector_store: Any | None = None) -> None:
        """Initialize with optional vector store for DB-first data."""
        self._vector_store = vector_store

        # Try to connect to vector store if not provided
        if self._vector_store is None and VECTOR_DB_AVAILABLE:
            try:
                self._vector_store = VectorStore()
            except Exception as e:
                logger.debug(f"Could not initialize VectorStore: {e}")

    def fetch_yield_channel_data(  # noqa: C901
        self,
        symbol: str,
        years: int = 10,
        use_db: bool = True,
        document: Any | None = None,
        min_price_rows: int | None = None,
        min_yield_rows: int | None = None,
        library_only: bool = False,
    ) -> YieldChannelData | None:
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

        Returns:
            YieldChannelData or None if data unavailable
        """
        if not DEPS_AVAILABLE:
            return None

        # Try vector DB first for historical dividend data
        db_dividend_history = None
        db_streak = None
        doc_to_use = document

        if use_db and self._vector_store:
            try:
                doc_to_use = document or self._vector_store.get_by_symbol(symbol)
                if doc_to_use and doc_to_use.dividend_history:
                    db_dividend_history = doc_to_use.dividend_history
                    db_streak = doc_to_use.dividend_streak_years
                    logger.debug(f"{symbol}: Found {len(db_dividend_history)} dividends in DB")
            except Exception as e:
                logger.debug(f"Vector DB lookup failed for {symbol}: {e}")

        try:
            ticker = yf.Ticker(symbol)

            # Get company name
            company_name = symbol
            if doc_to_use and doc_to_use.name:
                company_name = doc_to_use.name
            else:
                try:
                    info = ticker.info
                    company_name = info.get("shortName") or info.get("longName") or symbol
                except Exception:  # noqa: S110
                    pass

            # Get historical prices
            from utils.yfinance_history import fetch_price_history_with_fallback

            min_p = min_price_rows if min_price_rows is not None else 200
            hist, price_source = fetch_price_history_with_fallback(
                symbol,
                years=years,
                document=doc_to_use,
                min_rows=min_p,
                library_only=library_only,
            )
            if hist.empty or len(hist) < min_p:
                return None

            # Get dividend data - prefer DB data if available and substantial
            if db_dividend_history and len(db_dividend_history) >= 20:
                hist = self._integrate_db_dividends(hist, db_dividend_history)
            elif "Dividends" not in hist.columns or hist["Dividends"].sum() == 0:
                return None

            # Calculate trailing 12-month dividend
            hist = self._calculate_ttm_dividend(hist)
            if hist is None or len(hist) < 100:
                return None

            # Calculate yield
            hist["Yield"] = (hist["Div_TTM"] / hist["Close"]) * 100

            # Filter valid yields (0.1% to 20% - reasonable range)
            hist = hist[(hist["Yield"] > 0.1) & (hist["Yield"] < 20)]
            min_y = min_yield_rows if min_yield_rows is not None else 100
            if len(hist) < min_y:
                return None

            # Statistical analysis using percentiles (Weiss methodology)
            yields = hist["Yield"].dropna()
            stats = self._calculate_yield_statistics(yields)

            # Current values
            current_price = float(hist["Close"].iloc[-1])
            current_div = float(hist["Div_TTM"].iloc[-1])
            current_yield = float(hist["Yield"].iloc[-1])

            # Calculate percentile of current yield
            # Using rank(pct=True) correctly handles ties
            percentile = float(yields.rank(pct=True).iloc[-1] * 100)

            # Determine zone based on percentile
            zone = self._determine_zone(percentile)
            zone_score = self._calculate_zone_score(percentile, zone)

            # Calculate price targets at different yield levels
            price_targets = self._calculate_price_targets(current_div, stats)

            # Calculate dividend growth metrics
            dividend_growth = self._calculate_dividend_growth(hist)

            return YieldChannelData(
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
                years_analyzed=years,
                data_points=len(hist),
                dividend_cagr_5y=dividend_growth.get("cagr_5y"),
                dividend_cagr_10y=dividend_growth.get("cagr_10y"),
                dividend_streak=db_streak,
            )

        except Exception as e:
            logger.error(f"Error fetching yield channel data for {symbol}: {e}")
            return None

    def _integrate_db_dividends(self, hist: pd.DataFrame, db_dividends: list[Any]) -> pd.DataFrame:
        """Integrate vector DB dividend data into price history."""
        try:
            # Build dividend series from DB
            div_data = {}
            for div in db_dividends:
                if hasattr(div, "ex_date") and hasattr(div, "amount"):
                    div_date = div.ex_date if isinstance(div.ex_date, date) else div.ex_date.date()
                    div_data[div_date] = div.amount

            if not div_data:
                return hist

            # Create a dividend series matching the index
            hist["DB_Dividends"] = 0.0
            for idx in hist.index:
                idx_date = idx.date() if hasattr(idx, "date") else idx
                if idx_date in div_data:
                    hist.loc[idx, "DB_Dividends"] = div_data[idx_date]

            # Use DB dividends if they provide better coverage
            if hist["DB_Dividends"].sum() > hist.get("Dividends", pd.Series([0])).sum():
                hist["Dividends"] = hist["DB_Dividends"]

            return hist
        except Exception:
            return hist

    def _calculate_ttm_dividend(self, hist: pd.DataFrame) -> pd.DataFrame | None:
        """Calculate trailing 12-month dividend at each point."""
        try:
            if "Dividends" not in hist.columns:
                return None

            dividends = hist["Dividends"]
            if dividends.sum() == 0:
                return None

            # Rolling 252 trading days (~1 year)
            hist["Div_TTM"] = dividends.rolling(window=252, min_periods=63).sum()

            # Fill gaps
            hist["Div_TTM"] = hist["Div_TTM"].ffill().bfill()

            # Replace zeros
            hist.loc[hist["Div_TTM"] == 0, "Div_TTM"] = np.nan
            hist["Div_TTM"] = hist["Div_TTM"].ffill()

            # Drop invalid rows
            hist = hist.dropna(subset=["Div_TTM", "Close"])

            return hist if len(hist) >= 100 else None
        except Exception:
            return None

    def _calculate_yield_statistics(self, yields: pd.Series[Any]) -> dict[str, float]:
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
            min_pct = float(zone_def["min_pct"])
            max_pct = float(zone_def["max_pct"])
            if min_pct <= percentile <= max_pct:
                return zone_name
        return "Fair Value"

    def _calculate_zone_score(self, percentile: float, _zone: str) -> float:
        """Calculate value score (0-100, higher = better value)."""
        # Percentile directly maps to score (higher yield = higher score)
        return percentile

    def _calculate_price_targets(
        self, current_dividend: float, stats: dict[str, float]
    ) -> dict[str, float]:
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

    def _calculate_dividend_growth(self, hist: pd.DataFrame) -> dict[str, float | None]:
        """Calculate dividend CAGR."""
        result: dict[str, float | None] = {"cagr_5y": None, "cagr_10y": None}

        try:
            if "Div_TTM" not in hist.columns:
                return result

            # Get annual values
            annual = hist["Div_TTM"].resample("YE").last().dropna()
            if len(annual) < 2:
                return result

            # Current year (use most recent)
            current = float(annual.iloc[-1])

            # 5-year CAGR
            if len(annual) >= 6:
                start_5 = float(annual.iloc[-6])
                if start_5 > 0 and current > 0:
                    result["cagr_5y"] = round(((current / start_5) ** (1 / 5) - 1) * 100, 1)

            # 10-year CAGR
            if len(annual) >= 11:
                start_10 = float(annual.iloc[-11])
                if start_10 > 0 and current > 0:
                    result["cagr_10y"] = round(((current / start_10) ** (1 / 10) - 1) * 100, 1)

        except Exception:  # noqa: S110
            pass

        return result

    def _ensure_dividends_on_history(self, hist: pd.DataFrame) -> pd.DataFrame:
        """Backward compatibility for tests."""
        return hist

    def _dividend_payment_count(self, hist: pd.DataFrame) -> int:
        """Backward compatibility for tests."""
        return int((hist["Dividends"] > 0).sum()) if "Dividends" in hist.columns else 0

    def create_yield_channel_chart(
        self,
        data: YieldChannelData,
        height: int = 600,
        show_annotations: bool = True,
    ) -> Any | None:
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

        from utils.chart_theme import DARK_PALETTE, style_yield_channel_figure, yield_zone_fill

        # Create figure with two subplots
        fig = make_subplots(
            rows=2,
            cols=1,
            row_heights=[0.65, 0.35],
            shared_xaxes=True,
            vertical_spacing=0.06,
            subplot_titles=(
                "Share price · yield-based valuation zones",
                f"Trailing dividend yield · {data.years_analyzed}Y history",
            ),
        )

        # Prepare data
        dates = list(data.dates)
        prices = list(data.prices)
        yields = list(data.yields)
        dividends = list(data.annual_dividends)

        # Build zone price lines
        df = pd.DataFrame(
            {
                "date": dates,
                "price": prices,
                "dividend": dividends,
            }
        )

        # Calculate price at each yield level over time
        df["expensive"] = df["dividend"] / (data.yield_10th / 100)
        df["caution"] = df["dividend"] / (data.yield_25th / 100)
        df["fair_value"] = df["dividend"] / (data.median_yield / 100)
        df["value"] = df["dividend"] / (data.yield_75th / 100)
        df["deep_value"] = df["dividend"] / (data.yield_90th / 100)

        # === TOP CHART: Price with zones ===

        # Add zone fills (from top to bottom)
        zones = [
            ("expensive", "caution", yield_zone_fill("Expensive"), "Expensive zone"),
            ("caution", "fair_value", yield_zone_fill("Caution"), "Caution zone"),
            ("fair_value", "value", yield_zone_fill("Fair Value"), "Fair value zone"),
            ("value", "deep_value", yield_zone_fill("Value"), "Value zone"),
        ]

        dates_rev = dates[::-1]
        for upper, lower, color, name in zones:
            upper_prices = df[upper].tolist()
            lower_prices = df[lower].tolist()

            fig.add_trace(
                go.Scatter(
                    x=dates + dates_rev,
                    y=upper_prices + lower_prices[::-1],
                    fill="toself",
                    fillcolor=color,
                    line={"width": 0},
                    name=name,
                    showlegend=False,
                    hoverinfo="skip",
                ),
                row=1,
                col=1,
            )

        # Add zone boundary lines
        from utils.chart_theme import YIELD_ZONE_COLORS

        zone_lines = [
            (
                "expensive",
                YIELD_ZONE_COLORS["Expensive"],
                "dash",
                f"Expensive (< {data.yield_10th:.1f}%)",
            ),
            (
                "caution",
                YIELD_ZONE_COLORS["Caution"],
                "dot",
                f"Caution (< {data.yield_25th:.1f}%)",
            ),
            (
                "fair_value",
                YIELD_ZONE_COLORS["Fair Value"],
                "solid",
                f"Fair value ({data.median_yield:.1f}%)",
            ),
            (
                "value",
                YIELD_ZONE_COLORS["Value"],
                "dot",
                f"Value (> {data.yield_75th:.1f}%)",
            ),
            (
                "deep_value",
                YIELD_ZONE_COLORS["Deep Value"],
                "dash",
                f"Deep value (> {data.yield_90th:.1f}%)",
            ),
        ]

        for col, color, dash, name in zone_lines:
            fig.add_trace(
                go.Scatter(
                    x=dates,
                    y=df[col].tolist(),
                    mode="lines",
                    name=name,
                    line={"color": color, "width": 1.25, "dash": dash},
                    hovertemplate=f"{name.split(' (')[0]}: $%{{y:.2f}}<extra></extra>",
                ),
                row=1,
                col=1,
            )

        # Actual price line (prominent)
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=prices,
                mode="lines",
                name=f"{data.symbol} price",
                line={"color": DARK_PALETTE["primary"], "width": 2.75},
                hovertemplate="<b>%{x|%b %d, %Y}</b><br>Price: $%{y:.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )

        # Current price marker with zone color
        zone_color = self.ZONES.get(data.zone, {}).get("color", DARK_PALETTE["primary"])
        fig.add_trace(
            go.Scatter(
                x=[dates[-1]],
                y=[data.current_price],
                mode="markers",
                name=f"Current ${data.current_price:.2f}",
                marker={
                    "size": 11,
                    "color": zone_color,
                    "symbol": "circle",
                    "line": {"width": 2, "color": DARK_PALETTE["text"]},
                },
                showlegend=False,
                hovertemplate=(
                    f"<b>Current price</b><br>${data.current_price:.2f}<br>"
                    f"{data.zone}<extra></extra>"
                ),
            ),
            row=1,
            col=1,
        )

        # === BOTTOM CHART: Yield history ===

        # Yield line
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=yields,
                mode="lines",
                name="Dividend yield",
                line={"color": DARK_PALETTE["yield_line"], "width": 2.25},
                fill="tozeroy",
                fillcolor=DARK_PALETTE["yield_fill"],
                hovertemplate="<b>%{x|%b %d, %Y}</b><br>Yield: %{y:.2f}%<extra></extra>",
            ),
            row=2,
            col=1,
        )

        # Zone thresholds
        yield_lines = [
            (data.yield_10th, YIELD_ZONE_COLORS["Expensive"], "dash", "10th pctl"),
            (data.yield_25th, YIELD_ZONE_COLORS["Caution"], "dot", "25th pctl"),
            (data.median_yield, YIELD_ZONE_COLORS["Fair Value"], "solid", "Median"),
            (data.yield_75th, YIELD_ZONE_COLORS["Value"], "dot", "75th pctl"),
            (data.yield_90th, YIELD_ZONE_COLORS["Deep Value"], "dash", "90th pctl"),
        ]

        for yval, color, dash, _label in yield_lines:
            fig.add_hline(
                y=yval,
                row=2,
                col=1,
                line={"color": color, "width": 1.1, "dash": dash},
                annotation={
                    "text": f"{yval:.1f}%",
                    "font": {"size": 9, "color": color},
                    "bgcolor": "rgba(15, 23, 42, 0.85)",
                    "bordercolor": color,
                    "borderwidth": 1,
                    "borderpad": 2,
                },
                annotation_position="right",
            )

        # Current yield marker
        fig.add_trace(
            go.Scatter(
                x=[dates[-1]],
                y=[data.current_yield],
                mode="markers",
                marker={
                    "size": 10,
                    "color": zone_color,
                    "symbol": "diamond",
                    "line": {"width": 2, "color": DARK_PALETTE["text"]},
                },
                showlegend=False,
                hovertemplate=(
                    f"<b>Current yield</b><br>{data.current_yield:.2f}%<br>"
                    f"{data.zone}<extra></extra>"
                ),
            ),
            row=2,
            col=1,
        )

        # === Layout ===
        fig.update_yaxes(title_text="Price ($)", tickprefix="$", row=1, col=1)
        fig.update_yaxes(title_text="Yield (%)", ticksuffix="%", row=2, col=1)
        style_yield_channel_figure(fig, height=height)

        # Add price target annotations on the right
        if show_annotations:
            annotations = [
                (data.expensive_price, f"${data.expensive_price:.0f}", YIELD_ZONE_COLORS["Expensive"], "Expensive"),
                (data.fair_value_price, f"${data.fair_value_price:.0f}", YIELD_ZONE_COLORS["Fair Value"], "Fair value"),
                (data.value_price, f"${data.value_price:.0f}", YIELD_ZONE_COLORS["Value"], "Value"),
            ]

            for price, text, color, label in annotations:
                fig.add_annotation(
                    x=1.01,
                    y=price,
                    xref="paper",
                    yref="y",
                    text=f"<b>{text}</b><br><span style='font-size:9px'>{label}</span>",
                    showarrow=True,
                    arrowhead=0,
                    arrowwidth=1,
                    arrowcolor=color,
                    ax=24,
                    ay=0,
                    font={"size": 10, "color": color},
                    align="left",
                    bgcolor=DARK_PALETTE["paper"],
                    bordercolor=color,
                    borderwidth=1,
                    borderpad=3,
                )

        return fig

    @staticmethod
    def get_zone_info(zone: str) -> dict[str, Any]:
        """Get zone information including color and emoji."""
        return cast(
            dict[str, Any],
            YieldChannelService.ZONES.get(
                zone,
                {
                    "color": "#9e9e9e",
                    "emoji": "⚪",
                    "min_pct": 0,
                    "max_pct": 100,
                },
            ),
        )

    @staticmethod
    def get_zone_color(zone: str) -> str:
        """Get color code for zone."""
        return str(YieldChannelService.ZONES.get(zone, {}).get("color", "#9e9e9e"))

    @staticmethod
    def get_zone_emoji(zone: str) -> str:
        """Get emoji for zone."""
        return str(YieldChannelService.ZONES.get(zone, {}).get("emoji", "⚪"))

    def format_analysis_summary(self, data: YieldChannelData) -> dict[str, Any]:
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
                f"Yield ({data.current_yield:.1f}%) near {data.years_analyzed}Y median ({data.median_yield:.1f}%). "  # noqa: E501
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
                f"📈 **Exceptional Value** • {data.symbol}'s current yield of {data.current_yield:.2f}% "  # noqa: E501
                f"is higher than {pct:.0f}% of the past {data.years_analyzed} years. "
                f"Per Weiss methodology, this indicates significant undervaluation. "
                f"The market is offering this dividend stream at a steep discount."
            )
        elif pct >= 75:
            return (
                f"✅ **Good Value** • At {data.current_yield:.2f}%, the yield is above the 75th percentile. "  # noqa: E501
                f"This is a favorable entry point for dividend-focused investors. "
                f"The price offers an above-average income return."
            )
        elif pct >= 50:
            return (
                f"🟡 **Fair Value** • The current {data.current_yield:.2f}% yield is near the historical median. "  # noqa: E501
                f"Neither significantly undervalued nor overvalued. "
                f"Suitable for systematic investment or holding existing positions."
            )
        elif pct >= 25:
            return (
                f"⚠️ **Below Average Value** • At {data.current_yield:.2f}%, yield is lower than {100 - pct:.0f}% "  # noqa: E501
                f"of historical observations. Price may have outrun fundamentals. "
                f"Consider waiting for a better entry point."
            )
        else:
            return (
                f"🛑 **Overvalued** • Current yield of {data.current_yield:.2f}% is in the bottom {pct:.0f}% "  # noqa: E501
                f"historically. The stock is priced for perfection. "
                f"Per Weiss: when yield is extremely low, the risk/reward is unfavorable."
            )


def _default_yield_channel_service() -> YieldChannelService:
    """Return a default YieldChannelService instance."""
    return YieldChannelService()


def fetch_yield_channel_data(symbol: str, years: int = 10) -> YieldChannelData | None:
    """Convenience function for backward compatibility."""
    service = YieldChannelService()
    return service.fetch_yield_channel_data(symbol, years)


def create_yield_channel_chart(data: YieldChannelData, height: int = 600) -> Any | None:
    """Convenience function for backward compatibility."""
    service = YieldChannelService()
    return service.create_yield_channel_chart(data, height)


def validate_yield_channel_data(data: Any) -> bool:
    """Convenience function for backward compatibility."""
    return data is not None


def is_available() -> bool:
    """Check if yield channel charting is available."""
    return PLOTLY_AVAILABLE and DEPS_AVAILABLE
