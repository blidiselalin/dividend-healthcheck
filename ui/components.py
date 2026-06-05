"""
Reusable UI components for Streamlit display.

This module provides display components optimized for dividend investor decision-making.
"""

from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from models.stock import StockData
from services.scoring import Recommendation
from utils.formatting import (
    format_currency,
    format_percent,
    format_number,
    format_large_number,
    format_years,
)

try:
    from services.yield_channel_chart import (
        YieldChannelService,
        is_available as yield_chart_available,
    )
    YIELD_CHART_AVAILABLE = yield_chart_available()
except ImportError:
    YIELD_CHART_AVAILABLE = False

try:
    from services.news_service import (
        NewsService,
        NewsSummary,
        is_available as news_available,
    )
    NEWS_AVAILABLE = news_available()
except ImportError:
    NEWS_AVAILABLE = False

try:
    from data_ingestion.vector_store import VectorStore
    from data_ingestion.models import StockDocument
    VECTOR_DB_AVAILABLE = True
except ImportError:
    VECTOR_DB_AVAILABLE = False

# Standard column configuration for comparison tables
COMPARISON_TABLE_CONFIG: Dict[str, Any] = {
    "Score": st.column_config.ProgressColumn(min_value=0, max_value=100),
    "Streak": st.column_config.NumberColumn(format="%d yrs"),
    "Yield %": st.column_config.NumberColumn(format="%.2f%%"),
    "CAGR %": st.column_config.NumberColumn(format="%.1f%%"),
    "Payout %": st.column_config.NumberColumn(format="%.0f%%"),
    "P/E": st.column_config.NumberColumn(format="%.1f"),
}

# Tier badge mapping
TIER_BADGES: Dict[str, str] = {
    "King": "👑",
    "Aristocrat": "🏆",
    "Achiever": "⭐",
    "Contender": "📈",
    "Starter": "🌱",
}


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
    
    # === KEY HIGHLIGHTS (Front Page) ===

    @staticmethod
    def display_key_highlights(
        data: StockData,
        score: int,
        rec: Recommendation,
    ) -> None:
        """Nine headline figures for dividend decisions — no duplicate sections below."""
        dh = data.dividend_history
        streak = dh.consecutive_years if dh else None
        cagr_5y = dh.cagr_5y if dh else None
        safety = data.dividend_safety_score
        income_10k = (
            f"${(data.dividend_yield_pct / 100) * 10000:,.0f}/yr"
            if data.dividend_yield_pct
            else "—"
        )

        r1 = st.columns(3)
        r1[0].metric("Score", f"{score}/100", rec.label)
        r1[1].metric("Yield", UIComponents.format_percent(data.dividend_yield_pct))
        r1[2].metric(
            "Dividend streak",
            UIComponents.format_years(streak),
            data.dividend_tier,
        )

        r2 = st.columns(3)
        r2[0].metric("5Y div growth", UIComponents.format_percent(cagr_5y))
        r2[1].metric("Payout ratio", UIComponents.format_percent(data.payout_ratio_pct, 0))
        r2[2].metric(
            "Safety",
            f"{safety:.0f}/100" if safety is not None else "—",
        )

        r3 = st.columns(3)
        r3[0].metric("Price", UIComponents.format_currency(data.price))
        r3[1].metric("P/E", UIComponents.format_number(data.trailing_pe, 1))
        r3[2].metric("Income on $10K", income_10k)

    @staticmethod
    def display_prime_metrics(data: StockData, score: int) -> None:
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
            delta = None
            if data.dividend_yield_pct:
                if data.dividend_yield_pct >= 3:
                    delta = "Above avg"
                elif data.dividend_yield_pct < 2:
                    delta = "Below avg"
            st.metric(
                "💰 Dividend Yield",
                UIComponents.format_percent(data.dividend_yield_pct),
                delta,
            )
        
        with col3:
            cagr = data.dividend_history.cagr_5y if data.dividend_history else None
            delta = None
            if cagr:
                if cagr >= 7:
                    delta = "Strong growth"
                elif cagr < 3:
                    delta = "Slow growth"
            st.metric(
                "📈 5Y Div Growth",
                UIComponents.format_percent(cagr),
                delta,
            )
        
        # Row 2: Safety, Value, Income
        col4, col5, col6 = st.columns(3)
        
        with col4:
            safety = data.dividend_safety_score
            if safety is not None:
                if safety >= 70:
                    delta = "Safe"
                elif safety >= 50:
                    delta = "Moderate"
                else:
                    delta = "At risk"
            else:
                delta = None
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
    def display_investment_thesis(pros: List[str], cons: List[str]) -> None:
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
            streak_label = UIComponents.format_years(streak) if streak else "N/A"
            st.metric("Consecutive Years", streak_label)
        with col2:
            st.metric("Current Yield", UIComponents.format_percent(data.dividend_yield_pct))
        with col3:
            st.metric("Annual Dividend", UIComponents.format_currency(data.dividend_rate))
        with col4:
            st.metric("Payout Ratio", UIComponents.format_percent(data.payout_ratio_pct, 0))
        
        # Growth metrics
        if data.dividend_history:
            st.markdown("**Dividend Growth History**")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("5-Year CAGR", UIComponents.format_percent(data.dividend_history.cagr_5y))
            with col2:
                st.metric("10-Year CAGR", UIComponents.format_percent(data.dividend_history.cagr_10y))
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
            st.markdown(f"**52W Range:** ${data.fifty_two_week_low:.2f} - ${data.fifty_two_week_high:.2f}")
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
            st.metric("Operating Margin", UIComponents.format_percent(data.operating_margin_pct))
    
    @staticmethod
    def display_performance(data: StockData) -> None:
        """Display price performance and analyst data."""
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Current Price", UIComponents.format_currency(data.price))
            if data.price_return_1y is not None:
                delta_color = "normal" if data.price_return_1y >= 0 else "inverse"
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
    def _build_comparison_row(peer: Dict[str, Any], is_current: bool = False) -> Dict[str, Any]:
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
    def _display_comparison_table(data: List[Dict[str, Any]]) -> None:
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
        current_score: int,
        sector_peers: List[Dict[str, Any]],
        external_competitors: Optional[List[Dict[str, Any]]] = None,
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
            message = f"{medal} **{current_stock.symbol}** ranks **#{current_rank}** of {total} dividend stocks in sector"
            
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
            st.markdown("**🔍 S&P 500 peers (same sector)**")
            st.caption(
                "Dividend-paying S&P 500 names from analysed stocks — "
                "ranked by yield quality and dividend history (not in your portfolio)."
            )
            ext_rows = [UIComponents._build_comparison_row(c) for c in external_competitors]
            UIComponents._display_comparison_table(ext_rows)
            
            # Show yield channel comparison for top reference stock
            if YIELD_CHART_AVAILABLE and external_competitors:
                top_ref = external_competitors[0]
                with st.expander(
                    f"📈 Yield Channel: {top_ref['symbol']} vs {current_stock.symbol}",
                    expanded=False
                ):
                    st.markdown(
                        f"Compare dividend yield history to see which stock offers "
                        f"better value based on historical yield ranges."
                    )
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**{current_stock.symbol}** (Your Stock)")
                        UIComponents._display_mini_yield_chart(current_stock.symbol)
                    with col2:
                        st.markdown(f"**{top_ref['symbol']}** (Reference)")
                        UIComponents._display_mini_yield_chart(top_ref['symbol'])
        
        # Insights
        UIComponents._display_comparison_insights(
            current_stock, current_score, sector_peers, external_competitors
        )
    
    @staticmethod
    def _display_mini_yield_chart(symbol: str) -> None:
        """Display a compact yield channel summary for comparison."""
        if not YIELD_CHART_AVAILABLE:
            st.caption("Yield chart unavailable")
            return
        
        try:
            from services.yield_channel_chart import _default_yield_channel_service

            service = _default_yield_channel_service()
            data = service.fetch_yield_channel_data(symbol, years=10)
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
                    delta_color="normal" if gap > 0 else "inverse"
                )
            
            # Percentile bar
            pct = data.percentile
            bar_color = analysis["zone_color"]
            st.markdown(f"""
            <div style="margin: 8px 0;">
                <div style="font-size: 0.8em; color: #666;">Yield Percentile</div>
                <div style="background: #e0e0e0; border-radius: 4px; height: 8px; margin-top: 4px;">
                    <div style="background: {bar_color}; width: {pct}%; height: 100%; border-radius: 4px;"></div>
                </div>
                <div style="font-size: 0.75em; color: #888; text-align: right;">{pct:.0f}th percentile</div>
            </div>
            """, unsafe_allow_html=True)
            
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
        current_score: int,
        peers: List[Dict[str, Any]],
        externals: List[Dict[str, Any]],
    ) -> None:
        """Display comparison insights."""
        insights: List[str] = []
        warnings: List[str] = []
        
        if peers:
            yields = [p["dividend_yield_pct"] for p in peers if p["dividend_yield_pct"]]
            streaks = [p["div_streak"] for p in peers if p["div_streak"]]
            
            if yields and current.dividend_yield_pct:
                avg_yield = sum(yields) / len(yields)
                diff = current.dividend_yield_pct - avg_yield
                if diff > 0.5:
                    insights.append(f"Yield {diff:.1f}pp above sector avg")
                elif diff < -0.5:
                    warnings.append(f"Yield {abs(diff):.1f}pp below sector avg")
            
            if streaks and current.dividend_history:
                avg_streak = sum(streaks) / len(streaks)
                my_streak = current.dividend_history.consecutive_years
                if my_streak > avg_streak + 5:
                    insights.append(f"Longer dividend streak than peers")
                elif my_streak < avg_streak - 5:
                    warnings.append(f"Shorter streak than sector avg")
        
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
        *,
        channel_data=None,
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
            st.info("📊 Yield channel charts require `plotly` package. Install with: `pip install plotly`")
            return False
        
        from services.yield_channel_chart import _default_yield_channel_service

        service = _default_yield_channel_service()

        if channel_data is None:
            with st.spinner(f"Analyzing {years}-year dividend yield history..."):
                data = service.fetch_yield_channel_data(symbol, years)
        else:
            data = channel_data

        if data is None:
            st.warning(
                f"Insufficient dividend history for **{symbol}** yield channel analysis "
                "(needs ~5+ years of dividends and prices in the shared library). "
                "Try **Reload live data**, or re-enrich this symbol: "
                "`./scripts/update_cloud_docker.sh --ingest`."
            )
            return False
        
        from ui.charts import show_chart
        from utils.chart_theme import YIELD_ZONE_COLORS

        analysis = service.format_analysis_summary(data)

        if show_header:
            st.markdown("### Dividend Yield Channels · *Dividends Don't Lie*")
            st.caption(
                f"Geraldine Weiss (1988): yield vs its own history shows if price is fair. "
                f"{data.data_points:,} weekly points · ${data.current_dividend:.2f}/yr dividend today."
            )

        zone_color = YIELD_ZONE_COLORS.get(data.zone, "#0f766e")
        headline, sub = st.columns([1, 2])
        with headline:
            st.markdown(
                f"<p style='margin:0;font-size:1.45rem;font-weight:600;color:{zone_color}'>"
                f"{analysis['zone_emoji']} {data.zone}</p>"
                f"<p style='margin:0;color:#64748b;font-size:0.9rem'>"
                f"Yield percentile {data.percentile:.0f}% · {analysis['action']}</p>",
                unsafe_allow_html=True,
            )
        with sub:
            m1, m2, m3 = st.columns(3)
            m1.metric("Current yield", f"{data.current_yield:.2f}%", f"{analysis['yield_vs_median']:+.2f}pp vs median")
            m2.metric("Share price", f"${data.current_price:.2f}", f"Fair ≈ ${data.fair_value_price:.2f}")
            m3.metric(
                "Median yield (10Y)",
                f"{data.median_yield:.2f}%",
                f"Range {data.min_yield:.1f}–{data.max_yield:.1f}%",
            )

        st.caption(analysis["action_detail"])

        with st.expander("How to read this chart", expanded=False):
            st.markdown(
                """
                **Top — price**  
                Green → red bands are *fixed* levels implied by today’s dividend at historical yields
                (not wavy lines). The teal line is the actual share price.

                **Bottom — yield**  
                Orange = trailing dividend yield. Dashed lines = 10Y percentiles.
                **Higher yield usually means a cheaper price** vs this stock’s past.

                | Zone | Typical read |
                |------|----------------|
                | Deep Value / Value | Yield high vs history — investigate for entry |
                | Fair Value | Near median yield — hold / accumulate |
                | Caution / Expensive | Yield low vs history — patience or trim |
                """
            )

        fig = service.create_yield_channel_chart(data, height=480, show_annotations=False)
        if fig:
            show_chart(fig, key=f"yield_channel_{symbol}")

        st.markdown("#### Price targets at today’s dividend")
        zone_to_label = {
            "Expensive": "Expensive",
            "Caution": "Caution",
            "Fair Value": "Fair",
            "Value": "Value",
            "Deep Value": "Deep value",
        }
        tcols = st.columns(5)
        targets = [
            ("Expensive", data.expensive_price, data.yield_10th),
            ("Caution", data.caution_price, data.yield_25th),
            ("Fair", data.fair_value_price, data.median_yield),
            ("Value", data.value_price, data.yield_75th),
            ("Deep value", data.deep_value_price, data.yield_90th),
        ]
        for col, (label, price, yld) in zip(tcols, targets):
            active = zone_to_label.get(data.zone) == label
            with col:
                st.metric(
                    label + (" ←" if active else ""),
                    f"${price:.2f}",
                    f"at {yld:.1f}% yield",
                )

        # Educational section with Weiss methodology
        with st.expander("📖 Understanding the Dividends Don't Lie Strategy", expanded=False):
            st.markdown("""
            ### The Geraldine Weiss Methodology
            
            > *"Dividends don't lie. A company can fudge earnings, but it cannot fake a cash dividend."*
            > — **Geraldine Weiss**, Investment Quality Trends (1966)
            
            Geraldine Weiss revolutionized dividend investing with her book **"Dividends Don't Lie"** (1988). 
            Her core insight: **a stock's dividend yield is the most honest indicator of its value**.
            
            #### 🎯 The Core Principle
            
            | When Yield Is... | The Stock Is... | Action |
            |------------------|-----------------|--------|
            | **High** (above historical avg) | **Undervalued** | Consider buying |
            | **Average** (near historical norm) | **Fairly priced** | Hold or accumulate |
            | **Low** (below historical avg) | **Overvalued** | Avoid or take profits |
            
            #### 📊 How This Chart Works
            
            1. **Historical Yield Analysis**: We analyze 10 years of dividend yield data
            2. **Percentile Zones**: Yields are ranked into percentiles (not arbitrary cutoffs)
            3. **Price Targets**: Based on current dividend, we calculate prices at each yield level
            4. **Actionable Signals**: Clear zones indicate when to buy, hold, or wait
            
            #### 🏆 Best Practices from Top Investors
            
            **Warren Buffett** on dividends:
            > *"If you aren't willing to own a stock for ten years, don't even think about owning it for ten minutes."*
            
            **Benjamin Graham** on value:
            > *"The margin of safety is always dependent on the price paid."*
            
            #### ✅ When to Use This Strategy
            
            - Blue-chip dividend growth stocks with 10+ year dividend histories
            - Companies with consistent, growing dividends
            - Stable, mature businesses (utilities, consumer staples, healthcare)
            
            #### ❌ When NOT to Use This Strategy
            
            - New dividend payers (insufficient history)
            - Cyclical companies (dividends fluctuate)
            - High-growth stocks (dividends not relevant to value)
            - Companies with declining dividends
            
            #### 📈 The Power of Mean Reversion
            
            Yield channels work because yields tend to revert to historical averages. When:
            - Yield is HIGH → Price is LOW → Likely to rise → **BUY opportunity**
            - Yield is LOW → Price is HIGH → May correct → **WAIT for better entry**
            
            This creates a disciplined, emotion-free framework for timing dividend stock purchases.
            """)
        
        return True
    
    # === NEWS SUMMARY ===
    
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
            st.info(
                "📰 News summary requires `yfinance`. "
                "Install with: `pip install yfinance`"
            )
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
        st.markdown(f"### 📰 Latest News & Sentiment")
        
        # Sentiment overview row
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            emoji = display["sentiment_emoji"]
            sentiment = display["sentiment"].title()
            st.metric(
                "Overall Sentiment",
                f"{emoji} {sentiment}",
                f"Score: {display['sentiment_score']:+.2f}",
                delta_color="normal" if display["sentiment_score"] >= 0 else "inverse"
            )
        
        with col2:
            st.metric(
                "Articles Found",
                display["article_count"],
                f"Past {days} days"
            )
        
        with col3:
            st.metric(
                "Positive",
                display["positive_count"],
                delta_color="off"
            )
        
        with col4:
            st.metric(
                "Negative",
                display["negative_count"],
                delta_color="off"
            )
        
        # Key themes
        if display["key_themes"]:
            themes_str = " • ".join([t.title() for t in display["key_themes"]])
            st.caption(f"**Key Themes:** {themes_str}")
        
        # Highlights and Risks in two columns
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
        
        # Recent articles expandable
        with st.expander(f"📄 Recent Articles ({len(summary.articles)})", expanded=False):
            for article in summary.articles[:10]:
                # Sentiment indicator
                if article.sentiment == "positive":
                    sent_icon = "🟢"
                elif article.sentiment == "negative":
                    sent_icon = "🔴"
                else:
                    sent_icon = "⚪"
                
                # Date formatting
                date_str = ""
                if article.published_at:
                    date_str = article.published_at.strftime("%b %d, %Y")
                
                # Article card
                st.markdown(f"""
                <div style="
                    border-left: 3px solid {'#4caf50' if article.sentiment == 'positive' else '#f44336' if article.sentiment == 'negative' else '#9e9e9e'};
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
                """, unsafe_allow_html=True)
                
                if article.summary:
                    st.caption(article.summary[:200] + "..." if len(article.summary) > 200 else article.summary)
                
                if article.url:
                    st.markdown(f"[Read more]({article.url})")
                
                st.markdown("---")
        
        # Sources footer
        if display["sources"]:
            sources_str = ", ".join(display["sources"])
            st.caption(f"**Sources:** {sources_str} • Updated: {display['last_updated']}")
        
        return True
    
    @staticmethod
    def display_news_sentiment_badge(symbol: str) -> Optional[str]:
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
            sentiment = display["sentiment"].title()
            
            color = display["sentiment_color"]
            st.markdown(f"""
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
            """, unsafe_allow_html=True)
            
            return sentiment
            
        except Exception:
            return None
    
    # === VECTOR DATABASE DATA DISPLAY ===
    
    @staticmethod
    def display_vector_db_data(symbol: str, *, document=None) -> bool:
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
            st.warning(
                "📦 Vector database not available. "
                "Install with: `pip install chromadb`"
            )
            return False
        
        try:
            doc = document
            if doc is None:
                store = VectorStore()
                doc = store.get_by_symbol(symbol.upper())
            
            if doc is None:
                st.info(
                    f"📭 No data found for **{symbol}** in the vector database. "
                    f"Run `python ingest_data.py --enrich` to populate."
                )
                return False
            
            # Header
            st.markdown(f"### 📦 Vector Database: {doc.symbol}")
            st.caption(
                f"Source: {doc.source.value} • "
                f"Last Updated: {doc.last_updated.strftime('%Y-%m-%d %H:%M') if doc.last_updated else 'N/A'} • "
                f"Quality: {doc.data_quality:.0f}%"
            )
            
            # === BASIC INFO ===
            st.markdown("#### 📋 Basic Information")
            basic_info = [
                ("Symbol", doc.symbol),
                ("Company Name", doc.name),
                ("Sector", doc.sector),
                ("Industry", doc.industry),
                ("Exchange", doc.exchange),
            ]
            
            basic_df = pd.DataFrame(basic_info, columns=["Field", "Value"])
            st.dataframe(
                basic_df,
                hide_index=True,
                width="stretch",
            )
            
            # === DIVIDEND METRICS ===
            st.markdown("#### 💰 Dividend Metrics")
            
            dividend_info = [
                ("Dividend Yield", f"{doc.dividend_yield:.2f}%" if doc.dividend_yield else "N/A"),
                ("Annual Dividend", f"${doc.annual_dividend:.2f}" if doc.annual_dividend else "N/A"),
                ("Dividend Streak", f"{doc.dividend_streak_years} years" if doc.dividend_streak_years else "N/A"),
                ("Payout Ratio", f"{doc.payout_ratio:.1f}%" if doc.payout_ratio else "N/A"),
            ]
            
            # Determine tier
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
            st.dataframe(
                div_df,
                hide_index=True,
                width="stretch",
            )
            
            # === PRICE DATA ===
            st.markdown("#### 📈 Price Data")
            
            price_info = [
                ("Current Price", f"${doc.current_price:.2f}" if doc.current_price else "N/A"),
                ("Market Cap", UIComponents.format_large_number(doc.market_cap) if doc.market_cap else "N/A"),
                ("P/E Ratio", f"{doc.pe_ratio:.2f}" if doc.pe_ratio else "N/A"),
            ]
            
            price_df = pd.DataFrame(price_info, columns=["Metric", "Value"])
            st.dataframe(
                price_df,
                hide_index=True,
                width="stretch",
            )
            
            # === HISTORICAL DATA SUMMARY ===
            st.markdown("#### 📊 Historical Data")
            
            # Price history summary
            price_hist_count = len(doc.price_history) if doc.price_history else 0
            div_hist_count = len(doc.dividend_history) if doc.dividend_history else 0
            
            hist_info = [
                ("Price History Records", f"{price_hist_count:,} days"),
                ("Dividend History Records", f"{div_hist_count:,} payments"),
            ]
            
            # Add date ranges if available
            if doc.price_history and len(doc.price_history) > 0:
                sorted_prices = sorted(doc.price_history, key=lambda x: x.date)
                hist_info.append((
                    "Price History Range",
                    f"{sorted_prices[0].date} to {sorted_prices[-1].date}"
                ))
            
            if doc.dividend_history and len(doc.dividend_history) > 0:
                sorted_divs = sorted(doc.dividend_history, key=lambda x: x.ex_date)
                hist_info.append((
                    "Dividend History Range",
                    f"{sorted_divs[0].ex_date} to {sorted_divs[-1].ex_date}"
                ))
                
                # Calculate annual dividend from history
                annual_total = sum(d.amount for d in doc.dividend_history[-4:])
                hist_info.append(("Last 4 Dividends Total", f"${annual_total:.2f}"))
            
            hist_df = pd.DataFrame(hist_info, columns=["Data", "Value"])
            st.dataframe(
                hist_df,
                hide_index=True,
                width="stretch",
            )
            
            # === DIVIDEND HISTORY TABLE (if available) ===
            if doc.dividend_history and len(doc.dividend_history) > 0:
                with st.expander(f"📅 Dividend Payment History ({div_hist_count} records)", expanded=False):
                    # Show most recent dividends
                    recent_divs = sorted(doc.dividend_history, key=lambda x: x.ex_date, reverse=True)[:20]
                    
                    div_table = []
                    for d in recent_divs:
                        div_table.append({
                            "Ex-Date": d.ex_date.strftime("%Y-%m-%d"),
                            "Payment Date": d.payment_date.strftime("%Y-%m-%d") if d.payment_date else "N/A",
                            "Amount": f"${d.amount:.4f}",
                            "Frequency": d.frequency.title(),
                        })
                    
                    div_history_df = pd.DataFrame(div_table)
                    st.dataframe(
                        div_history_df,
                        hide_index=True,
                        width="stretch",
                    )
                    
                    if len(doc.dividend_history) > 20:
                        st.caption(f"Showing most recent 20 of {len(doc.dividend_history)} records")
            
            # === PRICE HISTORY TABLE (if available) ===
            if doc.price_history and len(doc.price_history) > 0:
                with st.expander(f"📈 Price History ({price_hist_count} records)", expanded=False):
                    # Show most recent prices
                    recent_prices = sorted(doc.price_history, key=lambda x: x.date, reverse=True)[:20]
                    
                    price_table = []
                    for p in recent_prices:
                        price_table.append({
                            "Date": p.date.strftime("%Y-%m-%d"),
                            "Open": f"${p.open:.2f}",
                            "High": f"${p.high:.2f}",
                            "Low": f"${p.low:.2f}",
                            "Close": f"${p.close:.2f}",
                            "Volume": f"{p.volume:,}",
                        })
                    
                    price_history_df = pd.DataFrame(price_table)
                    st.dataframe(
                        price_history_df,
                        hide_index=True,
                        width="stretch",
                    )
                    
                    if len(doc.price_history) > 20:
                        st.caption(f"Showing most recent 20 of {len(doc.price_history)} records")
            
            # === METADATA ===
            st.markdown("#### ℹ️ Metadata")
            
            meta_info = [
                ("Document ID", doc.document_id),
                ("Data Source", doc.source.value),
                ("Last Updated", doc.last_updated.strftime("%Y-%m-%d %H:%M:%S") if doc.last_updated else "N/A"),
                ("Data Quality Score", f"{doc.data_quality:.0f}/100"),
            ]
            
            if doc.description:
                meta_info.append(("Description", doc.description[:100] + "..." if len(doc.description) > 100 else doc.description))
            
            if doc.notes:
                meta_info.append(("Notes", doc.notes[:100] + "..." if len(doc.notes) > 100 else doc.notes))
            
            meta_df = pd.DataFrame(meta_info, columns=["Field", "Value"])
            st.dataframe(
                meta_df,
                hide_index=True,
                width="stretch",
            )
            
            # === RAW JSON EXPORT ===
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
                sector_df = pd.DataFrame([
                    {"Sector": k, "Count": v} 
                    for k, v in stats["sectors"].items()
                ])
                st.dataframe(sector_df, hide_index=True, width="stretch")
            
            return True
            
        except Exception as e:
            st.error(f"Error loading database stats: {e}")
            return False
