"""
Reusable UI components for Streamlit display.

This module provides display components optimized for dividend investor decision-making.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from data_ingestion.models import StockDocument
from models.stock import StockData
from utils.formatting import (
    format_currency,
    format_large_number,
    format_number,
    format_percent,
    format_years,
)

try:
    from services.yield_channel_chart import (
        is_available as yield_chart_available,
    )

    YIELD_CHART_AVAILABLE = yield_chart_available()
except ImportError:
    YIELD_CHART_AVAILABLE = False

try:
    from services.news_service import (
        NewsService,
    )
    from services.news_service import (
        is_available as news_available,
    )

    NEWS_AVAILABLE = news_available()
except ImportError:
    NEWS_AVAILABLE = False

try:
    from data_ingestion.vector_store import VectorStore

    VECTOR_DB_AVAILABLE = True
except ImportError:
    VECTOR_DB_AVAILABLE = False

# Standard column configuration for comparison tables
COMPARISON_TABLE_CONFIG: dict[str, Any] = {
    "Score": st.column_config.ProgressColumn(min_value=0, max_value=100),
    "Streak": st.column_config.NumberColumn(format="%d yrs"),
    "Yield %": st.column_config.NumberColumn(format="%.2f%%"),
    "CAGR %": st.column_config.NumberColumn(format="%.1f%%"),
    "Payout %": st.column_config.NumberColumn(format="%.0f%%"),
    "P/E": st.column_config.NumberColumn(format="%.1f"),
}

# Tier badge mapping
TIER_BADGES: dict[str, str] = {
    "King": "👑",
    "Aristocrat": "🏆",
    "Achiever": "⭐",
    "Contender": "📈",
    "Starter": "🌱",
}


def _get_yield_delta(yield_pct: float | None) -> str | None:
    if not yield_pct:
        return None
    if yield_pct >= 3:
        return "Above avg"
    if yield_pct < 2:
        return "Below avg"
    return None


def _get_cagr_delta(cagr: float | None) -> str | None:
    if not cagr:
        return None
    if cagr >= 7:
        return "Strong growth"
    if cagr < 3:
        return "Slow growth"
    return None


def _get_safety_delta(safety: float | None) -> str | None:
    if safety is None:
        return None
    if safety >= 70:
        return "Safe"
    if safety >= 50:
        return "Moderate"
    return "At risk"


def _analyze_yield_diff(
    current_yield: float | None, yields: list[float], insights: list[str], warnings: list[str]
) -> None:
    if yields and current_yield:
        avg_yield = sum(yields) / len(yields)
        diff = current_yield - avg_yield
        if diff > 0.5:
            insights.append(f"Yield {diff:.1f}pp above sector avg")
        elif diff < -0.5:
            warnings.append(f"Yield {abs(diff):.1f}pp below sector avg")


def _analyze_streak_diff(
    consecutive_years: int | None, streaks: list[int], insights: list[str], warnings: list[str]
) -> None:
    if streaks and consecutive_years:
        avg_streak = sum(streaks) / len(streaks)
        if consecutive_years > avg_streak + 5:
            insights.append("Longer dividend streak than peers")
        elif consecutive_years < avg_streak - 5:
            warnings.append("Shorter streak than sector avg")


class UIComponents:
    """Reusable UI display components for dividend analysis."""

    # Re-export formatting functions as static methods for backward compatibility
    format_currency = staticmethod(format_currency)
    format_percent = staticmethod(format_percent)
    format_number = staticmethod(format_number)
    format_large_number = staticmethod(format_large_number)
    format_years = staticmethod(format_years)

    @staticmethod
    def get_tier_badge(tier: str) -> str:
        """Get badge emoji for dividend tier."""
        return TIER_BADGES.get(tier, "")

    # === PRIME METRICS (Front Page) ===

    @staticmethod
    def display_prime_metrics(data: StockData, _score: int) -> None:
        """Display the 6 most important metrics for dividend investors.

        This is the key decision-making view shown prominently.
        """
        # Row 1: Dividend Streak & Yield (The Core)
        col1, col2, col3 = st.columns(3)

        with col1:
            streak = data.dividend_history.consecutive_years if data.dividend_history else 0
            tier = data.dividend_tier
            badge = UIComponents.get_tier_badge(tier)
            st.metric(
                f"{badge} Dividend Streak",
                UIComponents.format_years(streak),
                tier,
            )

        with col2:
            delta = _get_yield_delta(data.dividend_yield_pct)
            st.metric(
                "💰 Dividend Yield",
                UIComponents.format_percent(data.dividend_yield_pct),
                delta,
            )

        with col3:
            cagr = data.dividend_history.cagr_5y if data.dividend_history else None
            delta = _get_cagr_delta(cagr)
            st.metric(
                "📈 5Y Div Growth",
                UIComponents.format_percent(cagr),
                delta,
            )

        # Row 2: Safety, Value, Income
        col4, col5, col6 = st.columns(3)

        with col4:
            delta = _get_safety_delta(data.dividend_safety_score)
            safety = data.dividend_safety_score
            st.metric(
                "🛡️ Dividend Safety",
                f"{safety:.0f}/100" if safety else "N/A",
                delta,
            )

        with col5:
            st.metric(
                "📊 Payout Ratio",
                UIComponents.format_percent(data.payout_ratio_pct, 0),
            )

        with col6:
            # Annual income per $10K invested
            if data.dividend_yield_pct:
                annual_income = (data.dividend_yield_pct / 100) * 10000
                st.metric(
                    "💵 Income/$10K",
                    f"${annual_income:,.0f}/yr",
                )
            else:
                st.metric("💵 Income/$10K", "N/A")

    @staticmethod
    def display_quick_stats(data: StockData) -> None:
        """Display quick stats bar for at-a-glance view."""
        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            st.metric("Price", UIComponents.format_currency(data.price))
        with col2:
            st.metric("P/E", UIComponents.format_number(data.trailing_pe, 1))
        with col3:
            st.metric("Mkt Cap", UIComponents.format_large_number(data.market_cap))
        with col4:
            st.metric("D/E", UIComponents.format_number(data.debt_to_equity, 2))
        with col5:
            st.metric("ROE", UIComponents.format_percent(data.roe_pct))

    # === INVESTMENT THESIS ===

    @staticmethod
    def display_investment_thesis(pros: list[str], cons: list[str]) -> None:
        """Display investment thesis with strengths and concerns."""
        col1, col2 = st.columns(2)

        with col1:
            if pros:
                st.success("**✓ Strengths**\n" + "\n".join(f"• {p}" for p in pros))
            else:
                st.info("No notable strengths identified")

        with col2:
            if cons:
                st.warning("**⚠ Concerns**\n" + "\n".join(f"• {c}" for c in cons))
            else:
                st.info("No major concerns identified")

    @staticmethod
    def display_recommendation(rec_label: str, score: int, confidence: float = 100) -> None:
        """Display final recommendation with score and confidence."""
        confidence_note = f" (Data: {confidence:.0f}%)" if confidence < 100 else ""
        message = f"**{rec_label}** — Score: {score}/100{confidence_note}"

        if score >= 65:
            st.success(message)
        elif score >= 50:
            st.warning(message)
        else:
            st.error(message)

    # === DETAILED SECTIONS ===

    @staticmethod
    def display_dividend_details(data: StockData) -> None:
        """Display comprehensive dividend information."""
        # Primary dividend metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            streak = data.dividend_history.consecutive_years if data.dividend_history else None
            st.metric("Consecutive Years", UIComponents.format_years(streak))
        with col2:
            st.metric("Current Yield", UIComponents.format_percent(data.dividend_yield_pct))
        with col3:
            st.metric("Annual Dividend", UIComponents.format_currency(data.dividend_rate))
        with col4:
            st.metric("Payout Ratio", UIComponents.format_percent(data.payout_ratio_pct, 0))

        # Latest declared dividend
        last_div_val = getattr(data, "last_dividend_value", None)
        last_div_date = getattr(data, "last_dividend_date", None)
        if last_div_val is not None:
            date_str = f" ({last_div_date}" + ")" if last_div_date else ""
            st.info(f"**Latest Declared Dividend:** ${last_div_val:.4f}/share{date_str}")

        # Growth metrics
        if data.dividend_history:
            st.markdown("**Dividend Growth History**")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    "5-Year CAGR",
                    UIComponents.format_percent(data.dividend_history.cagr_5y),
                )
            with col2:
                st.metric(
                    "10-Year CAGR",
                    UIComponents.format_percent(data.dividend_history.cagr_10y),
                )
            with col3:
                st.metric("Data Years", f"{data.dividend_history.total_years} years")

            if data.dividend_history.ex_dividend_date:
                st.caption(f"Next Ex-Dividend: {data.dividend_history.ex_dividend_date}")

        # Safety indicators
        st.markdown("**Dividend Safety**")
        col1, col2 = st.columns(2)
        with col1:
            safety = data.dividend_safety_score
            if safety is not None:
                if safety >= 70:
                    st.success(f"Safety Score: {safety:.0f}/100 — Low risk of cut")
                elif safety >= 50:
                    st.warning(f"Safety Score: {safety:.0f}/100 — Monitor closely")
                else:
                    st.error(f"Safety Score: {safety:.0f}/100 — Elevated risk")
            else:
                st.info("Safety score unavailable")
        with col2:
            if data.dividend_coverage:
                st.metric("EPS Coverage", f"{data.dividend_coverage:.1f}x")

    @staticmethod
    def display_valuation_metrics(data: StockData) -> None:
        """Display valuation metrics."""
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("P/E (TTM)", UIComponents.format_number(data.trailing_pe, 1))
            st.metric("PEG Ratio", UIComponents.format_number(data.peg_ratio, 2))
        with col2:
            st.metric("P/E (Forward)", UIComponents.format_number(data.forward_pe, 1))
            st.metric("Price/Book", UIComponents.format_number(data.price_to_book, 2))
        with col3:
            st.metric("EV/EBITDA", UIComponents.format_number(data.ev_ebitda, 1))
            st.metric("Market Cap", UIComponents.format_large_number(data.market_cap))

        # Price context
        if data.fifty_two_week_low and data.fifty_two_week_high:
            st.markdown(
                f"**52W Range:** ${data.fifty_two_week_low:.2f} - ${data.fifty_two_week_high:.2f}"
            )
            if data.price_to_52w_high_pct:
                pct = data.price_to_52w_high_pct
                if pct <= -15:
                    st.success(f"📉 {abs(pct):.1f}% below 52-week high — potential value")
                elif pct >= -5:
                    st.info(f"Near 52-week high ({pct:.1f}%)")

    @staticmethod
    def display_financial_health(data: StockData) -> None:
        """Display financial health metrics with status indicators."""
        col1, col2, col3 = st.columns(3)

        with col1:
            if data.debt_to_equity is None:
                st.metric("Debt/Equity", "N/A")
            else:
                st.metric("Debt/Equity", f"{data.debt_to_equity:.2f}")
                if data.debt_to_equity <= 0.5:
                    st.caption("✓ Low debt")
                elif data.debt_to_equity <= 1.0:
                    st.caption("○ Moderate debt")
                else:
                    st.caption("⚠ High debt")

        with col2:
            if data.current_ratio is None:
                st.metric("Current Ratio", "N/A")
            else:
                st.metric("Current Ratio", f"{data.current_ratio:.2f}")
                if data.current_ratio >= 1.5:
                    st.caption("✓ Strong liquidity")
                elif data.current_ratio >= 1.0:
                    st.caption("○ Adequate")
                else:
                    st.caption("⚠ Low liquidity")

        with col3:
            if data.interest_coverage:
                st.metric("Interest Coverage", f"{data.interest_coverage:.1f}x")
                if data.interest_coverage >= 5:
                    st.caption("✓ Well covered")
                elif data.interest_coverage >= 2:
                    st.caption("○ Adequate")
                else:
                    st.caption("⚠ Tight")
            else:
                st.metric("Quick Ratio", UIComponents.format_number(data.quick_ratio, 2))

    @staticmethod
    def display_profitability(data: StockData) -> None:
        """Display profitability metrics."""
        col1, col2 = st.columns(2)

        with col1:
            st.metric("Return on Equity", UIComponents.format_percent(data.roe_pct))
            st.metric("Return on Assets", UIComponents.format_percent(data.roa_pct))
        with col2:
            st.metric("Profit Margin", UIComponents.format_percent(data.profit_margin_pct))
            st.metric(
                "Operating Margin",
                UIComponents.format_percent(data.operating_margin_pct),
            )

    @staticmethod
    def display_performance(data: StockData) -> None:
        """Display price performance and analyst data."""
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Current Price", UIComponents.format_currency(data.price))
            if data.price_return_1y is not None:
                st.metric("1Y Price Return", f"{data.price_return_1y:+.1f}%")
            if data.total_return_1y is not None:
                st.metric("1Y Total Return", f"{data.total_return_1y:+.1f}%")

        with col2:
            if data.target_price and data.price:
                st.metric(
                    "Analyst Target",
                    f"${data.target_price:.2f}",
                    f"{data.target_upside_pct:+.1f}%" if data.target_upside_pct else None,
                )
            else:
                st.metric("Analyst Target", "N/A")
            if data.analyst_rating:
                st.markdown(f"**Consensus:** {data.analyst_rating.upper()}")

        with col3:
            st.metric("Beta", UIComponents.format_number(data.beta, 2))
            if data.num_analysts:
                st.markdown(f"**# Analysts:** {data.num_analysts}")

    # === COMPARISON TABLES ===

    @staticmethod
    def _build_comparison_row(peer: dict[str, Any], is_current: bool = False) -> dict[str, Any]:
        """Build a row for comparison tables."""
        symbol = peer["symbol"]
        tier_badge = UIComponents.get_tier_badge(peer.get("dividend_tier", ""))

        if is_current:
            symbol = f"**{symbol}** ←"
        elif tier_badge:
            symbol = f"{tier_badge} {symbol}"

        return {
            "Symbol": symbol,
            "Company": (peer.get("name") or peer["symbol"])[:18],
            "Score": peer["score"],
            "Streak": peer.get("div_streak"),
            "Yield %": peer.get("dividend_yield_pct"),
            "CAGR %": peer.get("div_cagr"),
            "Payout %": peer.get("payout_ratio_pct"),
            "P/E": peer.get("trailing_pe"),
        }

    @staticmethod
    def _display_comparison_table(data: list[dict[str, Any]]) -> None:
        """Display comparison DataFrame with standard configuration."""
        if not data:
            return
        df = pd.DataFrame(data)
        st.dataframe(
            df,
            width="stretch",
            hide_index=True,
            column_config=COMPARISON_TABLE_CONFIG,
        )

    @staticmethod
    def display_sector_comparison(
        current_stock: StockData,
        _current_score: int,
        sector_peers: list[dict[str, Any]],
        external_competitors: list[dict[str, Any]] | None = None,
        _yield_channels: dict[str, Any] | None = None,
        _vector_docs: dict[str, Any] | None = None,
    ) -> None:
        """
        Display sector comparison with ranked peers.

        Implements "Dividends Don't Lie" philosophy:
        - Prioritizes dividend history and consistency
        - Shows yield channel analysis for top comparisons
        - Highlights stocks with proven dividend track records
        """
        sector = current_stock.sector
        external_competitors = external_competitors or []

        if not sector_peers and not external_competitors:
            st.info(f"No stocks found in {sector} for comparison")
            return

        st.subheader(f"🏭 {sector} Sector Comparison")

        # Philosophy note
        st.caption(
            "📖 *\"Dividends Don't Lie\"* — A company's dividend policy is a more "
            "honest indicator of financial health than reported earnings. (G. Weiss, 1988)"
        )

        # Determine ranking
        current_rank = next(
            (i + 1 for i, p in enumerate(sector_peers) if p["symbol"] == current_stock.symbol),
            len(sector_peers) + 1,
        )
        total = len(sector_peers)

        # Display ranking
        if total > 0 and current_rank <= total:
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            medal = medals.get(current_rank, "")
            message = (
                f"{medal} **{current_stock.symbol}** ranks **#{current_rank}** "
                f"of {total} dividend stocks in sector"
            )

            if current_rank == 1:
                st.success(message)
            elif current_rank <= 3:
                st.info(message)
            else:
                st.warning(message)

        # Sector peers table
        st.markdown("**📊 Dividend Stocks in Sector:**")
        rows = [
            UIComponents._build_comparison_row(p, is_current=(p["symbol"] == current_stock.symbol))
            for p in sector_peers
        ]
        if rows:
            UIComponents._display_comparison_table(rows)
        else:
            st.caption("No other dividend stocks in this sector")

        # External reference stocks (top public dividend payers NOT in config)
        if external_competitors:
            st.markdown("---")
            st.markdown("**🔍 Top Reference Stocks (Not in Analysis List):**")
            st.caption(
                "These are highly-rated public dividend payers in the same sector "
                "for comparison — not part of your current analysis list."
            )
            ext_rows = [UIComponents._build_comparison_row(c) for c in external_competitors]
            UIComponents._display_comparison_table(ext_rows)

            # Show yield channel comparison for top reference stock
            if YIELD_CHART_AVAILABLE and external_competitors:
                top_ref = external_competitors[0]
                with st.expander(
                    f"📈 Yield Channel: {top_ref['symbol']} vs {current_stock.symbol}",
                    expanded=False,
                ):
                    st.markdown(
                        "Compare dividend yield history to see which stock offers "
                        "better value based on historical yield ranges."
                    )

                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**{current_stock.symbol}** (Your Stock)")
                        UIComponents._display_mini_yield_chart(current_stock.symbol)
                    with col2:
                        st.markdown(f"**{top_ref['symbol']}** (Reference)")
                        UIComponents._display_mini_yield_chart(top_ref["symbol"])

        # Insights
        UIComponents._display_comparison_insights(
            current_stock, _current_score, sector_peers, external_competitors
        )

    @staticmethod
    def _display_mini_yield_chart(
        symbol: str,
        channel_data: Any | None = None,
        vector_doc: Any | None = None,
    ) -> None:
        """Display a compact yield channel summary for comparison."""
        if not YIELD_CHART_AVAILABLE:
            st.caption("Yield chart unavailable")
            return

        try:
            from services.yield_channel_chart import YieldChannelService

            service = YieldChannelService()
            data = channel_data or service.fetch_yield_channel_data(
                symbol,
                years=10,
                use_db=True,
                document=vector_doc,
            )
            if data is None:
                st.caption(f"Insufficient data for {symbol}")
                return

            analysis = service.format_analysis_summary(data)
            zone_emoji = analysis["zone_emoji"]

            # Compact grid
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Current Yield", f"{data.current_yield:.2f}%")
                st.metric("Median Yield", f"{data.median_yield:.2f}%")
            with col2:
                st.metric("Zone", f"{zone_emoji} {data.zone}")
                gap = analysis["gap_to_fair_pct"]
                st.metric(
                    "vs Fair Value",
                    f"{gap:+.1f}%",
                    delta_color="normal" if gap > 0 else "inverse",
                )

            # Percentile bar
            pct = data.percentile
            bar_color = analysis["zone_color"]
            st.markdown(
                f"""
            <div style="margin: 8px 0;">
                <div style="font-size: 0.8em; color: #666;">Yield Percentile</div>
                <div style="background: #e0e0e0; border-radius: 4px; height: 8px; margin-top: 4px;">
                    <div style="background: {bar_color}; width: {pct}%;
                                height: 100%; border-radius: 4px;"></div>
                </div>
                <div style="font-size: 0.75em; color: #888;
                            text-align: right;">{pct:.0f}th percentile</div>
            </div>
            """,
                unsafe_allow_html=True,
            )

            # Quick assessment
            if data.zone in ["Deep Value", "Value"]:
                st.success(f"**{analysis['action']}** — Yield above historical norm")
            elif data.zone in ["Expensive", "Caution"]:
                st.warning(f"**{analysis['action']}** — Yield below historical norm")
            else:
                st.info(f"**{analysis['action']}** — Near fair value")

        except Exception as e:
            st.caption(f"Could not load yield data: {e}")

    @staticmethod
    def _display_comparison_insights(
        current: StockData,
        _current_score: int,
        peers: list[dict[str, Any]],
        _externals: list[dict[str, Any]],
    ) -> None:
        """Display comparison insights."""
        insights: list[str] = []
        warnings: list[str] = []

        if peers:
            yields = [p["dividend_yield_pct"] for p in peers if p["dividend_yield_pct"]]
            streaks = [p["div_streak"] for p in peers if p["div_streak"]]
            _analyze_yield_diff(current.dividend_yield_pct, yields, insights, warnings)
            _analyze_streak_diff(
                current.dividend_history.consecutive_years if current.dividend_history else None,
                streaks,
                insights,
                warnings,
            )

        if insights or warnings:
            st.markdown("**Insights:**")
            col1, col2 = st.columns(2)
            with col1:
                for i in insights:
                    st.markdown(f"✓ {i}")
            with col2:
                for w in warnings:
                    st.markdown(f"⚠ {w}")

    # === DIVIDEND YIELD CHANNELS CHART ===

    @staticmethod
    def display_yield_channel_chart(
        symbol: str,
        years: int = 10,
        channel_data: Any | None = None,
        vector_doc: Any | None = None,
        show_header: bool = True,
    ) -> bool:
        """
        Display enhanced Dividend Yield Channels chart with Geraldine Weiss methodology.

        Implements the "Dividends Don't Lie" strategy:
        - Buy when yield is ABOVE historical average (price is depressed)
        - Avoid/sell when yield is BELOW historical average (price is elevated)
        - Use percentile-based zones for more robust analysis

        Args:
            symbol: Stock ticker symbol
            years: Years of historical data to analyze

        Returns:
            True if chart was displayed, False otherwise
        """
        if not YIELD_CHART_AVAILABLE:
            st.info(
                "📊 Yield channel charts require `plotly` package. "
                "Install with: `pip install plotly`"
            )
            return False

        # Use the enhanced service
        from services.yield_channel_chart import YieldChannelService

        service = YieldChannelService()

        with st.spinner(f"Analyzing {years}-year dividend yield history..."):
            data = channel_data or service.fetch_yield_channel_data(
                symbol,
                years,
                use_db=True,
                document=vector_doc,
            )

        if data is None:
            st.warning(f"Insufficient dividend history for {symbol} yield channel analysis")
            return False

        # Get formatted analysis
        analysis = service.format_analysis_summary(data)

        if show_header:
            # Header with Weiss methodology attribution
            st.markdown("### 📊 Dividend Yield Channels • *Dividends Don't Lie*")
            st.caption(
                f"Analysis based on Geraldine Weiss methodology (1988) • "
                f"{data.data_points:,} data points over {years} years"
            )

        # Main metrics row
        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            zone_emoji = analysis["zone_emoji"]
            st.metric(
                "Valuation Zone",
                f"{zone_emoji} {data.zone}",
                f"Percentile: {data.percentile:.0f}%",
                delta_color="normal" if data.percentile >= 50 else "inverse",
            )

        with col2:
            delta = analysis["yield_vs_median"]
            delta_str = f"{delta:+.2f}pp vs median"
            st.metric(
                "Current Yield",
                f"{data.current_yield:.2f}%",
                delta_str,
                delta_color="normal" if delta >= 0 else "inverse",
            )

        with col3:
            gap = analysis["gap_to_fair_pct"]
            st.metric(
                "Fair Value",
                f"${data.fair_value_price:.2f}",
                f"{gap:+.1f}% gap",
                delta_color="normal" if gap > 0 else "inverse",
            )

        with col4:
            st.metric(
                "Median Yield",
                f"{data.median_yield:.2f}%",
                f"10Y Range: {data.min_yield:.1f}-{data.max_yield:.1f}%",
            )

        with col5:
            if data.dividend_cagr_5y is not None:
                growth_delta = "Growing" if data.dividend_cagr_5y > 0 else "Declining"
                st.metric(
                    "5Y Div CAGR",
                    f"{data.dividend_cagr_5y:+.1f}%",
                    growth_delta,
                    delta_color="normal" if data.dividend_cagr_5y > 0 else "inverse",
                )
            else:
                st.metric("Annual Dividend", f"${data.current_dividend:.2f}", "Per share")

        # Action recommendation with color-coded styling
        action = analysis["action"]
        action_detail = analysis["action_detail"]

        if data.zone in ["Deep Value", "Value"]:
            st.success(f"**{action}** • {action_detail}")
        elif data.zone == "Fair Value":
            st.info(f"**{action}** • {action_detail}")
        elif data.zone == "Caution":
            st.warning(f"**{action}** • {action_detail}")
        else:
            st.error(f"**{action}** • {action_detail}")

        # Weiss interpretation
        weiss_text = service.get_weiss_interpretation(data)
        st.markdown(weiss_text)

        # Interactive chart
        fig = service.create_yield_channel_chart(data, height=600, show_annotations=True)
        if fig:
            st.plotly_chart(fig, width="stretch")

        # Price targets grid
        st.markdown("---")
        st.markdown("#### 🎯 Yield-Based Price Targets")
        st.caption("Based on historical yield percentiles and current annual dividend")

        cols = st.columns(5)

        targets = [
            (
                "🔴 Expensive",
                data.expensive_price,
                f"<{data.yield_10th:.1f}%",
                "#f44336",
            ),
            ("🟠 Caution", data.caution_price, f"<{data.yield_25th:.1f}%", "#ff9800"),
            (
                "🟡 Fair Value",
                data.fair_value_price,
                f"≈{data.median_yield:.1f}%",
                "#ffc107",
            ),
            ("🟢 Value", data.value_price, f">{data.yield_75th:.1f}%", "#4caf50"),
            (
                "💎 Deep Value",
                data.deep_value_price,
                f">{data.yield_90th:.1f}%",
                "#1b5e20",
            ),
        ]

        for col, (label, price, yield_range, color) in zip(cols, targets, strict=False):
            pct_from_current = ((price / data.current_price) - 1) * 100
            is_current = (
                (label == "💎 Deep Value" and data.zone == "Deep Value")
                or (label == "🟢 Value" and data.zone == "Value")
                or (label == "🟡 Fair Value" and data.zone == "Fair Value")
                or (label == "🟠 Caution" and data.zone == "Caution")
                or (label == "🔴 Expensive" and data.zone == "Expensive")
            )

            with col:
                border = "3px solid" if is_current else "1px solid"
                color_class = "green" if pct_from_current > 0 else "red"
                st.markdown(
                    f"""
                <div style="
                    border: {border} {color};
                    border-radius: 8px;
                    padding: 12px;
                    text-align: center;
                    background: {"rgba(0,0,0,0.05)" if is_current else "transparent"};
                ">
                    <div style="font-weight: bold; margin-bottom: 4px;">{label}</div>
                    <div style="font-size: 1.3em; color: {color}; font-weight: bold;">
                        ${price:.2f}
                    </div>
                    <div style="font-size: 0.85em; color: #666;">
                        Yield {yield_range}
                    </div>
                    <div style="font-size: 0.8em; color: {color_class};">
                        {pct_from_current:+.1f}% from now
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

        # Educational section with Weiss methodology
        with st.expander("📖 Understanding the Dividends Don't Lie Strategy", expanded=False):
            st.markdown(
                "### The Geraldine Weiss Methodology\n\n"
                "> *\"Dividends don't lie. A company can fudge earnings, "
                'but it cannot fake a cash dividend."*\n'
                "> — **Geraldine Weiss**, Investment Quality Trends (1966)\n\n"
                "Geraldine Weiss revolutionized dividend investing with her book "
                '**"Dividends Don\'t Lie"** (1988).\n'
                "Her core insight: **a stock's dividend yield is the most honest "
                "indicator of its value**.\n\n"
                "#### 🎯 The Core Principle\n\n"
                "| When Yield Is... | The Stock Is... | Action |\n"
                "|------------------|-----------------|--------|\n"
                "| **High** (above historical avg) | **Undervalued** | Consider buying |\n"
                "| **Average** (near historical norm) | **Fairly priced** | Hold or accumulate |\n"
                "| **Low** (below historical avg) | **Overvalued** | Avoid or take profits |\n\n"
                "#### 📊 How This Chart Works\n\n"
                "1. **Historical Yield Analysis**: We analyze 10 years of dividend yield data\n"
                "2. **Percentile Zones**: Yields are ranked into percentiles "
                "(not arbitrary cutoffs)\n"
                "3. **Price Targets**: Based on current dividend, we calculate prices at each "
                "yield level\n"
                "4. **Actionable Signals**: Clear zones indicate when to buy, hold, or wait\n\n"
                "#### 🏆 Best Practices from Top Investors\n\n"
                "**Warren Buffett** on dividends:\n"
                "> *\"If you aren't willing to own a stock for ten years, "
                "don't even think about owning it for ten minutes.\"*\n\n"
                "**Benjamin Graham** on value:\n"
                '> *"The margin of safety is always dependent on the price paid."*\n\n'
                "#### ✅ When to Use This Strategy\n\n"
                "- Blue-chip dividend growth stocks with 10+ year dividend histories\n"
                "- Companies with consistent, growing dividends\n"
                "- Stable, mature businesses (utilities, consumer staples, healthcare)\n\n"
                "#### ❌ When NOT to Use This Strategy\n\n"
                "- New dividend payers (insufficient history)\n"
                "- Cyclical companies (dividends fluctuate)\n"
                "- High-growth stocks (dividends not relevant to value)\n"
                "- Companies with declining dividends\n\n"
                "#### 📈 The Power of Mean Reversion\n\n"
                "Yield channels work because yields tend to revert to historical averages. When:\n"
                "- Yield is HIGH → Price is LOW → Likely to rise → **BUY opportunity**\n"
                "- Yield is LOW → Price is HIGH → May correct → **WAIT for better entry**\n\n"
                "This creates a disciplined, emotion-free framework "
                "for timing dividend stock purchases."
            )

        return True

    # === NEWS SUMMARY ===

    @staticmethod
    def _render_news_metrics_row(display: dict[str, Any], days: int) -> None:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            emoji = display["sentiment_emoji"]
            sentiment = display["sentiment"].title()
            st.metric(
                "Overall Sentiment",
                f"{emoji} {sentiment}",
                f"Score: {display['sentiment_score']:+.2f}",
                delta_color="normal" if display["sentiment_score"] >= 0 else "inverse",
            )
        with col2:
            st.metric("Articles Found", display["article_count"], f"Past {days} days")
        with col3:
            st.metric("Positive", display["positive_count"], delta_color="off")
        with col4:
            st.metric("Negative", display["negative_count"], delta_color="off")

    @staticmethod
    def _render_news_highlights_and_risks(display: dict[str, Any]) -> None:
        if display["highlights"] or display["risks"]:
            col_left, col_right = st.columns(2)
            with col_left:
                if display["highlights"]:
                    st.markdown("**Positive Headlines:**")
                    for h in display["highlights"]:
                        st.markdown(f"- ✅ {h}")
            with col_right:
                if display["risks"]:
                    st.markdown("**Risk Headlines:**")
                    for r in display["risks"]:
                        st.markdown(f"- ⚠️ {r}")

    @staticmethod
    def display_news_summary(symbol: str, days: int = 7) -> bool:
        """
        Display financial news summary for a stock.

        Fetches news from top public financial sources:
        - Yahoo Finance
        - Google News

        Provides sentiment analysis and key highlights for dividend investors.

        Args:
            symbol: Stock ticker symbol
            days: Number of days to look back (default: 7)

        Returns:
            True if news was displayed, False otherwise
        """
        if not NEWS_AVAILABLE:
            st.info("📰 News summary requires `yfinance`. Install with: `pip install yfinance`")
            return False

        service = NewsService()

        with st.spinner(f"Fetching latest news for {symbol}..."):
            summary = service.fetch_news_summary(symbol, days=days)

        if not summary.articles:
            st.caption(f"No recent news found for {symbol} in the past {days} days")
            return False

        # Format for display
        display = service.format_summary_for_display(summary)

        # Header with sentiment indicator
        st.markdown("### 📰 Latest News & Sentiment")

        # Sentiment overview row
        UIComponents._render_news_metrics_row(display, days)

        # Key themes
        if display["key_themes"]:
            themes_str = " • ".join([t.title() for t in display["key_themes"]])
            st.caption(f"**Key Themes:** {themes_str}")

        # Highlights and Risks in two columns
        UIComponents._render_news_highlights_and_risks(display)

        # Recent articles expandable
        UIComponents._render_recent_articles_expander(summary.articles)

        # Sources footer
        if display["sources"]:
            sources_str = ", ".join(display["sources"])
            st.caption(f"**Sources:** {sources_str} • Updated: {display['last_updated']}")

        return True

    @staticmethod
    def _render_recent_articles_expander(articles: list[Any]) -> None:
        with st.expander(f"📄 Recent Articles ({len(articles)})", expanded=False):
            for article in articles[:10]:
                # Sentiment indicator
                if article.sentiment == "positive":
                    sent_icon = "🟢"
                    border_color = "#4caf50"
                elif article.sentiment == "negative":
                    sent_icon = "🔴"
                    border_color = "#f44336"
                else:
                    sent_icon = "⚪"
                    border_color = "#9e9e9e"

                # Date formatting
                date_str = ""
                if article.published_at:
                    date_str = article.published_at.strftime("%b %d, %Y")

                # Article card
                st.markdown(
                    f"""
                <div style="
                    border-left: 3px solid {border_color};
                    padding: 8px 12px;
                    margin: 8px 0;
                    background: rgba(0,0,0,0.02);
                    border-radius: 0 4px 4px 0;
                ">
                    <div style="font-weight: 500; margin-bottom: 4px;">
                        {sent_icon} {article.title}
                    </div>
                    <div style="font-size: 0.8em; color: #666;">
                        {article.source} • {date_str}
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

                if article.summary:
                    st.caption(
                        article.summary[:200] + "..."
                        if len(article.summary) > 200
                        else article.summary
                    )

                if article.url:
                    st.markdown(f"[Read more]({article.url})")

                st.markdown("---")

    @staticmethod
    def display_news_sentiment_badge(symbol: str) -> str | None:
        """
        Display a compact news sentiment badge.

        Returns the sentiment label or None if unavailable.
        """
        if not NEWS_AVAILABLE:
            return None

        try:
            service = NewsService()
            summary = service.fetch_news_summary(symbol, days=3, max_articles=5)

            if not summary.articles:
                return None

            display = service.format_summary_for_display(summary)
            emoji = display["sentiment_emoji"]
            sentiment = str(display["sentiment"].title())

            color = display["sentiment_color"]
            st.markdown(
                f"""
            <span style="
                background: {color}22;
                color: {color};
                padding: 2px 8px;
                border-radius: 12px;
                font-size: 0.85em;
                font-weight: 500;
            ">
                {emoji} {sentiment} ({summary.article_count} articles)
            </span>
            """,
                unsafe_allow_html=True,
            )

            return sentiment

        except Exception:
            return None

    # === VECTOR DATABASE DATA DISPLAY ===

    @staticmethod
    def _render_vdb_basic_and_dividend_info(doc: StockDocument) -> None:
        st.markdown("#### 📋 Basic Information")
        basic_info = [
            ("Symbol", doc.symbol),
            ("Company Name", doc.name),
            ("Sector", doc.sector),
            ("Industry", doc.industry),
            ("Exchange", doc.exchange),
        ]
        basic_df = pd.DataFrame(basic_info, columns=["Field", "Value"])
        st.dataframe(basic_df, hide_index=True, width="stretch")

        st.markdown("#### 💰 Dividend Metrics")
        dividend_info = [
            ("Dividend Yield", f"{doc.dividend_yield:.2f}%" if doc.dividend_yield else "N/A"),
            ("Annual Dividend", f"${doc.annual_dividend:.2f}" if doc.annual_dividend else "N/A"),
            (
                "Dividend Streak",
                f"{doc.dividend_streak_years} years" if doc.dividend_streak_years else "N/A",
            ),
            ("Payout Ratio", f"{doc.payout_ratio:.1f}%" if doc.payout_ratio else "N/A"),
        ]

        tier = "N/A"
        tier_badge = ""
        if doc.dividend_streak_years:
            if doc.dividend_streak_years >= 50:
                tier = "Dividend King"
                tier_badge = "👑"
            elif doc.dividend_streak_years >= 25:
                tier = "Dividend Aristocrat"
                tier_badge = "🏆"
            elif doc.dividend_streak_years >= 10:
                tier = "Dividend Achiever"
                tier_badge = "⭐"
            elif doc.dividend_streak_years >= 5:
                tier = "Dividend Contender"
                tier_badge = "📈"
            else:
                tier = "Dividend Starter"
                tier_badge = "🌱"

        dividend_info.append(("Dividend Tier", f"{tier_badge} {tier}"))
        div_df = pd.DataFrame(dividend_info, columns=["Metric", "Value"])
        st.dataframe(div_df, hide_index=True, width="stretch")

    @staticmethod
    def _render_vdb_price_and_history_summary(doc: StockDocument) -> None:
        st.markdown("#### 📈 Price Data")
        price_info = [
            ("Current Price", f"${doc.current_price:.2f}" if doc.current_price else "N/A"),
            (
                "Market Cap",
                UIComponents.format_large_number(doc.market_cap) if doc.market_cap else "N/A",
            ),
            ("P/E Ratio", f"{doc.pe_ratio:.2f}" if doc.pe_ratio else "N/A"),
        ]
        price_df = pd.DataFrame(price_info, columns=["Metric", "Value"])
        st.dataframe(price_df, hide_index=True, width="stretch")

        st.markdown("#### 📊 Historical Data")
        price_hist_count = len(doc.price_history) if doc.price_history else 0
        div_hist_count = len(doc.dividend_history) if doc.dividend_history else 0

        hist_info = [
            ("Price History Records", f"{price_hist_count:,} days"),
            ("Dividend History Records", f"{div_hist_count:,} payments"),
        ]

        if doc.price_history and len(doc.price_history) > 0:
            sorted_prices = sorted(doc.price_history, key=lambda x: x.date)
            hist_info.append(
                ("Price History Range", f"{sorted_prices[0].date} to {sorted_prices[-1].date}")
            )

        if doc.dividend_history and len(doc.dividend_history) > 0:
            sorted_divs = sorted(doc.dividend_history, key=lambda x: x.ex_date)
            hist_info.append(
                ("Dividend History Range", f"{sorted_divs[0].ex_date} to {sorted_divs[-1].ex_date}")
            )
            annual_total = sum(d.amount for d in doc.dividend_history[-4:])
            hist_info.append(("Last 4 Dividends Total", f"${annual_total:.2f}"))

        hist_df = pd.DataFrame(hist_info, columns=["Data", "Value"])
        st.dataframe(hist_df, hide_index=True, width="stretch")

    @staticmethod
    def _render_vdb_history_tables(doc: StockDocument) -> None:
        div_hist_count = len(doc.dividend_history) if doc.dividend_history else 0
        price_hist_count = len(doc.price_history) if doc.price_history else 0

        if doc.dividend_history and len(doc.dividend_history) > 0:
            with st.expander(
                f"📅 Dividend Payment History ({div_hist_count} records)", expanded=False
            ):
                recent_divs = sorted(doc.dividend_history, key=lambda x: x.ex_date, reverse=True)[
                    :20
                ]
                div_table = []
                for d in recent_divs:
                    div_table.append(
                        {
                            "Ex-Date": d.ex_date.strftime("%Y-%m-%d"),
                            "Payment Date": d.payment_date.strftime("%Y-%m-%d")
                            if d.payment_date
                            else "N/A",
                            "Amount": f"${d.amount:.4f}",
                            "Frequency": d.frequency.title(),
                        }
                    )
                st.dataframe(pd.DataFrame(div_table), hide_index=True, width="stretch")
                if len(doc.dividend_history) > 20:
                    st.caption(f"Showing most recent 20 of {len(doc.dividend_history)} records")

        if doc.price_history and len(doc.price_history) > 0:
            with st.expander(f"📈 Price History ({price_hist_count} records)", expanded=False):
                recent_prices = sorted(doc.price_history, key=lambda x: x.date, reverse=True)[:20]
                price_table = []
                for p in recent_prices:
                    price_table.append(
                        {
                            "Date": p.date.strftime("%Y-%m-%d"),
                            "Open": f"${p.open:.2f}",
                            "High": f"${p.high:.2f}",
                            "Low": f"${p.low:.2f}",
                            "Close": f"${p.close:.2f}",
                            "Volume": f"{p.volume:,}",
                        }
                    )
                st.dataframe(pd.DataFrame(price_table), hide_index=True, width="stretch")
                if len(doc.price_history) > 20:
                    st.caption(f"Showing most recent 20 of {len(doc.price_history)} records")

    @staticmethod
    def _render_vdb_metadata_and_json(doc: StockDocument) -> None:
        st.markdown("#### 📝 Metadata")
        last_updated_str = (
            doc.last_updated.strftime("%Y-%m-%d %H:%M:%S") if doc.last_updated else "N/A"
        )
        meta_info = [
            ("Document ID", doc.document_id),
            ("Data Source", doc.source.value),
            ("Last Updated", last_updated_str),
            ("Data Quality Score", f"{doc.data_quality:.0f}/100"),
        ]

        if doc.description:
            meta_info.append(
                (
                    "Description",
                    doc.description[:100] + "..."
                    if len(doc.description) > 100
                    else doc.description,
                )
            )
        if doc.notes:
            meta_info.append(
                ("Notes", doc.notes[:100] + "..." if len(doc.notes) > 100 else doc.notes)
            )

        meta_df = pd.DataFrame(meta_info, columns=["Field", "Value"])
        st.dataframe(meta_df, hide_index=True, width="stretch")

        with st.expander("🔧 Raw Data (JSON)", expanded=False):
            raw_data = {
                "symbol": doc.symbol,
                "name": doc.name,
                "sector": doc.sector,
                "industry": doc.industry,
                "exchange": doc.exchange,
                "dividend_yield": doc.dividend_yield,
                "annual_dividend": doc.annual_dividend,
                "dividend_streak_years": doc.dividend_streak_years,
                "payout_ratio": doc.payout_ratio,
                "current_price": doc.current_price,
                "market_cap": doc.market_cap,
                "pe_ratio": doc.pe_ratio,
                "source": doc.source.value,
                "last_updated": doc.last_updated.isoformat() if doc.last_updated else None,
                "data_quality": doc.data_quality,
                "price_history_count": len(doc.price_history) if doc.price_history else 0,
                "dividend_history_count": len(doc.dividend_history) if doc.dividend_history else 0,
                "description": doc.description,
                "notes": doc.notes,
            }
            import json

            st.code(json.dumps(raw_data, indent=2), language="json")

    @staticmethod
    def display_vector_db_data(
        symbol: str,
        document: StockDocument | None = None,
    ) -> bool:
        """
        Display all data stored in the vector database for a given ticker.

        Shows data in a clean, readable table format with sections for:
        - Basic Info
        - Dividend Metrics
        - Price Data
        - Historical Data Summary
        - Metadata

        Args:
            symbol: Stock ticker symbol

        Returns:
            True if data was displayed, False if no data found
        """
        if not VECTOR_DB_AVAILABLE:
            st.warning("📦 Vector database not available. Install with: `pip install chromadb`")
            return False

        try:
            store = VectorStore()
            doc = document or store.get_by_symbol(symbol.upper())

            if doc is None:
                st.info(
                    f"📭 No data found for **{symbol}** in the vector database. "
                    f"Run `python ingest_data.py --enrich` to populate."
                )
                return False

            # Header
            st.markdown(f"### 📦 Vector Database: {doc.symbol}")
            last_updated_str = (
                doc.last_updated.strftime("%Y-%m-%d %H:%M") if doc.last_updated else "N/A"
            )
            st.caption(
                f"Source: {doc.source.value} • "
                f"Last Updated: {last_updated_str} • "
                f"Quality: {doc.data_quality:.0f}%"
            )

            UIComponents._render_vdb_basic_and_dividend_info(doc)
            UIComponents._render_vdb_price_and_history_summary(doc)
            UIComponents._render_vdb_history_tables(doc)
            UIComponents._render_vdb_metadata_and_json(doc)

            return True

        except Exception as e:
            st.error(f"Error loading vector database data: {e}")
            return False

    @staticmethod
    def display_vector_db_stats() -> bool:
        """
        Display overall vector database statistics.

        Returns:
            True if stats were displayed, False otherwise
        """
        if not VECTOR_DB_AVAILABLE:
            st.warning("Vector database not available.")
            return False

        try:
            store = VectorStore()
            stats = store.get_stats()

            st.markdown("### 📊 Vector Database Statistics")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Total Documents", stats.get("total_documents", 0))

            with col2:
                st.metric("Dividend Kings", stats.get("dividend_kings", 0))

            with col3:
                st.metric("Aristocrats", stats.get("dividend_aristocrats", 0))

            with col4:
                st.metric("Unique Symbols", stats.get("unique_symbols", 0))

            # Sectors breakdown
            if stats.get("sectors"):
                st.markdown("#### Sectors")
                sector_df = pd.DataFrame(
                    [{"Sector": k, "Count": v} for k, v in stats["sectors"].items()]
                )
                st.dataframe(sector_df, hide_index=True, width="stretch")

            return True

        except Exception as e:
            st.error(f"Error loading database stats: {e}")
            return False
