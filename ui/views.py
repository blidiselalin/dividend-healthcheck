"""
Page views for the Streamlit application.

This module contains the main view classes optimized for dividend investors,
with key metrics prominently displayed on the first page.
"""

import time
from datetime import datetime
from typing import Optional, Tuple

import pandas as pd
import streamlit as st

from config import DIVIDEND_KINGS, API_DELAY_SECONDS, DATA_SOURCES
from models.stock import StockData
from services.stock_service import StockService
from services.scoring import ScoringService, Recommendation
from services.sector_service import SectorService
from ui.components import UIComponents

# Try to import Analysed-stocks-first service (primary data source)
try:
    from services.vectordb_service import VectorDBService, get_vectordb_service
    VECTORDB_SERVICE_AVAILABLE = True
except ImportError:
    VECTORDB_SERVICE_AVAILABLE = False

# Try to import enhanced service (fallback with API calls)
try:
    from services.enhanced_stock_service import EnhancedStockService
    _enhanced_service: Optional[EnhancedStockService] = None
    
    def _get_enhanced_service() -> EnhancedStockService:
        """Get or create the enhanced stock service singleton."""
        global _enhanced_service
        if _enhanced_service is None:
            _enhanced_service = EnhancedStockService(
                staleness_days=7,
                fetch_realtime_prices=True,
            )
        return _enhanced_service
    
    ENHANCED_SERVICE_AVAILABLE = True
except ImportError:
    ENHANCED_SERVICE_AVAILABLE = False


def get_stock_data(symbol: str) -> Optional[StockData]:
    """
    Get stock data, prioritizing VectorDB service.
    
    Order of preference:
    1. VectorDB service (if data is complete)
    2. EnhancedStockService (API with DB enrichment)
    3. Basic StockService (API only)
    """
    # Try VectorDB first
    if VECTORDB_SERVICE_AVAILABLE:
        try:
            vdb_service = get_vectordb_service()
            if vdb_service.is_available:
                data = vdb_service.get_stock(symbol)
                if data and vdb_service.is_data_complete(data):
                    return data
        except Exception:
            pass
    
    # Fallback to enhanced service
    if ENHANCED_SERVICE_AVAILABLE:
        service = _get_enhanced_service()
        return service.fetch(symbol)
    
    # Final fallback to basic service
    return StockService.fetch(symbol)


def get_service_status() -> dict:
    """Get status of the stock service."""
    status = {
        "mode": "API-only",
        "vector_db_available": False,
        "is_db_primary": False,
        "document_count": 0,
        "dividend_kings": 0,
    }
    
    if VECTORDB_SERVICE_AVAILABLE:
        try:
            vdb_service = get_vectordb_service()
            if vdb_service.is_available:
                stats = vdb_service.get_stats()
                doc_count = stats.get("total_documents", 0)
                status["mode"] = "Analysed-stocks-first"
                status["vector_db_available"] = True
                status["is_db_primary"] = doc_count > 0
                status["document_count"] = doc_count
                try:
                    from services.sp500_peers_service import coverage_stats
                    cov = coverage_stats()
                    status["sp500_coverage"] = cov
                except Exception:
                    status["sp500_coverage"] = None
                status["dividend_kings"] = stats.get("dividend_kings", 0)
        except Exception:
            pass
    
    if ENHANCED_SERVICE_AVAILABLE and status["mode"] == "API-only":
        status["mode"] = "Enhanced (API + DB)"
    
    return status


USE_ENHANCED_SERVICE = ENHANCED_SERVICE_AVAILABLE or VECTORDB_SERVICE_AVAILABLE

# Try to import PDF report generator
try:
    from services.report_generator import ReportGenerator, generate_stock_report
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


class SingleStockView:
    """View for analyzing a single dividend stock."""
    
    @staticmethod
    def _render_sidebar() -> Tuple[str, bool]:
        """Render sidebar controls.
        
        Returns:
            Tuple of (selected_symbol, show_sector_comparison).
        """
        st.sidebar.markdown("### Select Stock")

        preset_symbol = st.session_state.get("single_stock_symbol")
        default_symbol = preset_symbol if preset_symbol in DIVIDEND_KINGS else (
            "KO" if "KO" in DIVIDEND_KINGS else DIVIDEND_KINGS[0]
        )

        symbol = st.sidebar.selectbox(
            "Dividend Kings (50+ Years)",
            DIVIDEND_KINGS,
            index=DIVIDEND_KINGS.index(default_symbol) if default_symbol in DIVIDEND_KINGS else 0,
        )

        custom_default = ""
        if preset_symbol and preset_symbol not in DIVIDEND_KINGS:
            custom_default = preset_symbol
        custom_symbol = st.sidebar.text_input("Or enter any symbol:", value=custom_default)
        if custom_symbol:
            symbol = custom_symbol.upper().strip()
        else:
            st.session_state["single_stock_symbol"] = symbol
        
        st.sidebar.markdown("---")
        show_sector = st.sidebar.checkbox("Compare with sector peers", value=True)
        
        return symbol, show_sector
    
    @staticmethod
    def _render_header(data: StockData, rec: Recommendation) -> None:
        """Render stock header with tier badge."""
        tier_badge = UIComponents.get_tier_badge(data.dividend_tier)
        
        col1, col2 = st.columns([4, 1])
        with col1:
            st.header(f"{tier_badge} {data.name}")
            streak = data.dividend_history.consecutive_years if data.dividend_history else 0
            st.caption(
                f"**{data.symbol}** • {data.sector} • "
                f"{streak} years of dividend growth"
            )
        with col2:
            if rec.score >= 65:
                st.success(f"**{rec.label}**\n\nScore: {rec.score}")
            elif rec.score >= 50:
                st.warning(f"**{rec.label}**\n\nScore: {rec.score}")
            else:
                st.error(f"**{rec.label}**\n\nScore: {rec.score}")
    
    @classmethod
    def render_analysis_for_symbol(
        cls,
        symbol: str,
        *,
        show_sector: bool = True,
        data: Optional[StockData] = None,
        yield_channel_data=None,
        vector_doc=None,
    ) -> None:
        """Render the full single-stock dashboard for a symbol."""
        if data is None:
            with st.spinner(f"Loading data for {symbol}..."):
                data = get_stock_data(symbol)

        if not data:
            st.error(f"Could not fetch data for {symbol}. Please verify the symbol.")
            return

        score = ScoringService.calculate_score(data)
        confidence = data.data_quality_score or 100
        rec = ScoringService.get_recommendation(score, confidence)
        pros, cons = ScoringService.get_investment_thesis(data)

        cls._render_header(data, rec)

        from ui.analysis_evidence import render_analysis_evidence

        portfolio_at = st.session_state.get("portfolio_details_time")

        render_analysis_evidence(
            symbol,
            data=data,
            vector_doc=vector_doc,
            yield_channel_data=yield_channel_data,
            portfolio_prices_at=portfolio_at,
            expanded=True,
        )
        st.divider()

        st.subheader("📊 Key Dividend Metrics")
        UIComponents.display_prime_metrics(data, score)

        st.divider()
        UIComponents.display_quick_stats(data)

        st.divider()
        st.subheader("📋 Investment Analysis")
        UIComponents.display_investment_thesis(pros, cons)
        UIComponents.display_recommendation(rec.label, score, confidence)

        st.divider()
        with st.expander("📰 Latest News & Sentiment", expanded=True):
            UIComponents.display_news_summary(symbol, days=7)

        if show_sector and data.sector != "N/A":
            st.divider()
            with st.expander("🏭 Sector Comparison", expanded=True):
                with st.spinner(f"Loading {data.sector} peers..."):
                    sector_peers, external = SectorService.get_top_sector_peers(
                        data, score, include_external=True
                    )
                UIComponents.display_sector_comparison(data, score, sector_peers, external)

        st.divider()
        UIComponents.display_yield_channel_chart(
            symbol,
            years=10,
            channel_data=yield_channel_data,
            show_header=True,
        )

        st.divider()
        st.subheader("📖 Detailed Analysis")

        with st.expander("💰 Dividend Details"):
            UIComponents.display_dividend_details(data)

        with st.expander("📈 Valuation"):
            UIComponents.display_valuation_metrics(data)

        with st.expander("🏦 Financial Health"):
            UIComponents.display_financial_health(data)

        with st.expander("💹 Profitability"):
            UIComponents.display_profitability(data)

        with st.expander("🎯 Performance & Analysts"):
            UIComponents.display_performance(data)

        with st.expander("📦 Vector Database Data"):
            UIComponents.display_vector_db_data(symbol, document=vector_doc)

        st.divider()
        cls._render_report_section(data, score, rec, pros, cons, symbol)

        st.divider()
        cls._render_data_source_footer(
            data, confidence, symbol=symbol, vector_doc=vector_doc
        )

    @classmethod
    def render(cls) -> None:
        """Render the single stock analysis view."""
        symbol, show_sector = cls._render_sidebar()
        auto_analyze = st.session_state.pop("single_stock_auto_analyze", False)

        if not auto_analyze and not st.sidebar.button("Analyze", type="primary"):
            # Show empty state
            st.info("👈 Select a stock and click **Analyze** to begin")
            st.markdown("""
            ### What are Dividend Kings?
            
            **Dividend Kings** are elite companies that have increased their dividends 
            for **50 or more consecutive years**. This remarkable achievement demonstrates:
            
            - 📈 Consistent earnings power through multiple economic cycles
            - 💪 Strong financial discipline and shareholder commitment  
            - 🛡️ Resilient business models that withstand recessions
            
            Only ~50 companies in the U.S. have achieved this status.
            """)
            return

        cls.render_analysis_for_symbol(symbol, show_sector=show_sector)
    
    @classmethod
    def _render_report_section(
        cls,
        data: StockData,
        score: int,
        rec: Recommendation,
        pros: list,
        cons: list,
        symbol: str,
    ) -> None:
        """Render the report generation and export section."""
        st.subheader("📄 Research Report")
        
        # Report preview in a styled container
        with st.container():
            st.markdown(
                f"""
                <div style="border: 1px solid #ddd; border-radius: 8px; padding: 16px; 
                            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);">
                    <h4 style="margin: 0 0 8px 0; color: #1a237e;">
                        📊 {data.name} ({symbol}) - Research Report
                    </h4>
                    <p style="color: #666; margin: 0 0 12px 0;">
                        {data.dividend_tier} | {data.sector} | Generated {datetime.now().strftime('%B %d, %Y')}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        
        # Report contents preview
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Report Contents:**")
            st.markdown("""
            - Rate Card (Score, Key Metrics)
            - Dividend Analysis (Growth, Safety)
            - Valuation Analysis (P/E, Targets)
            - Investment Thesis (Pros/Cons)
            - Financial Strength Ratings
            """)
        
        with col2:
            # Key metrics preview box
            streak = data.dividend_history.consecutive_years if data.dividend_history else 0
            st.markdown("**Key Highlights:**")
            st.markdown(f"""
            - **Score:** {score}/100 ({rec.label})
            - **Yield:** {data.dividend_yield_pct:.2f}% 
            - **Streak:** {streak} years
            - **Payout:** {data.payout_ratio_pct:.0f}% of earnings
            """)
        
        st.markdown("")
        
        # Export buttons
        st.markdown("**Export Options:**")
        export_cols = st.columns([1, 1, 1, 2])
        
        with export_cols[0]:
            if REPORTLAB_AVAILABLE:
                # Generate PDF immediately for download
                try:
                    pdf_bytes = generate_stock_report(
                        stock=data,
                        score=score,
                        recommendation=rec.label,
                        pros=pros,
                        cons=cons,
                    )
                    st.download_button(
                        label="📥 PDF Report",
                        data=pdf_bytes,
                        file_name=f"Research_{symbol}_{datetime.now().strftime('%Y%m%d')}.pdf",
                        mime="application/pdf",
                        type="primary",
                        width="stretch",
                    )
                except Exception as e:
                    st.error(f"PDF Error: {e}")
            else:
                st.button("📥 PDF Report", disabled=True, width="stretch")
                st.caption("Install: `pip install reportlab`")
        
        with export_cols[1]:
            # CSV export of key metrics
            csv_data = cls._generate_csv_report(data, score, rec, pros, cons)
            st.download_button(
                label="📊 CSV Data",
                data=csv_data,
                file_name=f"Data_{symbol}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                width="stretch",
            )
        
        with export_cols[2]:
            # JSON export
            json_data = cls._generate_json_report(data, score, rec, pros, cons)
            st.download_button(
                label="📋 JSON",
                data=json_data,
                file_name=f"Report_{symbol}_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json",
                width="stretch",
            )
        
        with export_cols[3]:
            if not REPORTLAB_AVAILABLE:
                st.info("💡 Install `reportlab` for PDF reports")
    
    @staticmethod
    def _generate_csv_report(
        data: StockData,
        score: int,
        rec: Recommendation,
        pros: list,
        cons: list,
    ) -> str:
        """Generate CSV report data."""
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(["Metric", "Value"])
        writer.writerow([])
        
        # Basic Info
        writer.writerow(["=== COMPANY INFO ===", ""])
        writer.writerow(["Symbol", data.symbol])
        writer.writerow(["Company", data.name])
        writer.writerow(["Sector", data.sector])
        writer.writerow(["Industry", data.industry])
        writer.writerow([])
        
        # Score
        writer.writerow(["=== ANALYSIS ===", ""])
        writer.writerow(["Score", f"{score}/100"])
        writer.writerow(["Recommendation", rec.label])
        writer.writerow(["Dividend Tier", data.dividend_tier])
        writer.writerow([])
        
        # Key Metrics
        writer.writerow(["=== KEY METRICS ===", ""])
        writer.writerow(["Current Price", f"${data.price:.2f}" if data.price else "N/A"])
        writer.writerow(["Dividend Yield", f"{data.dividend_yield_pct:.2f}%" if data.dividend_yield_pct else "N/A"])
        writer.writerow(["Annual Dividend", f"${data.dividend_rate:.2f}" if data.dividend_rate else "N/A"])
        
        dh = data.dividend_history
        writer.writerow(["Consecutive Years", dh.consecutive_years if dh else "N/A"])
        writer.writerow(["5Y Div CAGR", f"{dh.cagr_5y:.2f}%" if dh and dh.cagr_5y else "N/A"])
        writer.writerow(["10Y Div CAGR", f"{dh.cagr_10y:.2f}%" if dh and dh.cagr_10y else "N/A"])
        writer.writerow([])
        
        # Safety
        writer.writerow(["=== DIVIDEND SAFETY ===", ""])
        writer.writerow(["Payout Ratio", f"{data.payout_ratio_pct:.1f}%" if data.payout_ratio_pct else "N/A"])
        writer.writerow(["FCF Payout", f"{data.fcf_payout_ratio_pct:.1f}%" if data.fcf_payout_ratio_pct else "N/A"])
        writer.writerow(["Dividend Coverage", f"{data.dividend_coverage:.2f}x" if data.dividend_coverage else "N/A"])
        writer.writerow([])
        
        # Valuation
        writer.writerow(["=== VALUATION ===", ""])
        writer.writerow(["P/E Ratio", f"{data.trailing_pe:.2f}" if data.trailing_pe else "N/A"])
        writer.writerow(["Forward P/E", f"{data.forward_pe:.2f}" if data.forward_pe else "N/A"])
        writer.writerow(["Price/Book", f"{data.price_to_book:.2f}" if data.price_to_book else "N/A"])
        writer.writerow(["Market Cap", f"${data.market_cap/1e9:.2f}B" if data.market_cap else "N/A"])
        writer.writerow([])
        
        # Financial Health
        writer.writerow(["=== FINANCIAL HEALTH ===", ""])
        writer.writerow(["Debt/Equity", f"{data.debt_to_equity:.2f}" if data.debt_to_equity else "N/A"])
        writer.writerow(["Current Ratio", f"{data.current_ratio:.2f}" if data.current_ratio else "N/A"])
        writer.writerow(["ROE", f"{data.roe_pct:.2f}%" if data.roe_pct else "N/A"])
        writer.writerow(["Operating Margin", f"{data.operating_margin_pct:.2f}%" if data.operating_margin_pct else "N/A"])
        writer.writerow([])
        
        # Thesis
        writer.writerow(["=== INVESTMENT THESIS ===", ""])
        writer.writerow(["Strengths", "; ".join(pros[:5])])
        writer.writerow(["Concerns", "; ".join(cons[:5])])
        writer.writerow([])
        
        writer.writerow(["Generated", datetime.now().strftime("%Y-%m-%d %H:%M")])
        
        return output.getvalue()
    
    @staticmethod
    def _generate_json_report(
        data: StockData,
        score: int,
        rec: Recommendation,
        pros: list,
        cons: list,
    ) -> str:
        """Generate JSON report data."""
        import json
        
        dh = data.dividend_history
        
        report = {
            "report_info": {
                "generated_at": datetime.now().isoformat(),
                "version": "1.0",
            },
            "company": {
                "symbol": data.symbol,
                "name": data.name,
                "sector": data.sector,
                "industry": data.industry,
                "dividend_tier": data.dividend_tier,
            },
            "analysis": {
                "score": score,
                "max_score": 100,
                "recommendation": rec.label,
                "confidence": rec.confidence if hasattr(rec, "confidence") else None,
            },
            "dividend_metrics": {
                "yield_pct": data.dividend_yield_pct,
                "annual_dividend": data.dividend_rate,
                "consecutive_years": dh.consecutive_years if dh else None,
                "cagr_5y": dh.cagr_5y if dh else None,
                "cagr_10y": dh.cagr_10y if dh else None,
                "ex_dividend_date": dh.ex_dividend_date if dh else None,
            },
            "safety_metrics": {
                "payout_ratio_pct": data.payout_ratio_pct,
                "fcf_payout_ratio_pct": data.fcf_payout_ratio_pct,
                "dividend_coverage": data.dividend_coverage,
            },
            "valuation": {
                "current_price": data.price,
                "pe_ratio": data.trailing_pe,
                "forward_pe": data.forward_pe,
                "price_to_book": data.price_to_book,
                "market_cap": data.market_cap,
            },
            "financial_health": {
                "debt_to_equity": data.debt_to_equity,
                "current_ratio": data.current_ratio,
                "roe_pct": data.roe_pct,
                "operating_margin_pct": data.operating_margin_pct,
            },
            "investment_thesis": {
                "strengths": pros[:5],
                "concerns": cons[:5],
            },
        }
        
        return json.dumps(report, indent=2, default=str)
    
    @staticmethod
    def _render_data_source_footer(
        data: StockData,
        confidence: float,
        *,
        symbol: str = "",
        vector_doc=None,
    ) -> None:
        """Render the data source footer with status information."""
        from ui.analysis_evidence import render_analysis_evidence_footer

        render_analysis_evidence_footer(
            symbol or data.symbol,
            data=data,
            vector_doc=vector_doc,
        )
        if USE_ENHANCED_SERVICE:
            status = get_service_status()
            if status.get("is_db_primary"):
                st.caption(
                    f"Analysed stocks library · {status.get('document_count', 0)} tickers loaded"
                )
            else:
                st.caption("Live API mode — run ingest to persist history locally")
        else:
            st.caption(f"Data: {DATA_SOURCES['primary']} (API only)")


class FullAnalysisView:
    """View for analyzing all Dividend Kings."""
    
    @staticmethod
    def _run_analysis() -> pd.DataFrame:
        """Run analysis on all Dividend Kings, prioritizing analysed stocks."""
        progress = st.progress(0)
        status = st.empty()
        
        results = []
        total = len(DIVIDEND_KINGS)
        db_hits = 0
        api_hits = 0
        
        # Try VectorDB first for batch loading
        if VECTORDB_SERVICE_AVAILABLE:
            vdb_service = get_vectordb_service()
            if vdb_service.is_available:
                stats = vdb_service.get_stats()
                status.text(f"Loading from Analysed stocks ({stats.get('total_documents', 0)} stocks cached)...")
                
                all_data = vdb_service.get_stocks(DIVIDEND_KINGS)
                
                for i, symbol in enumerate(DIVIDEND_KINGS):
                    progress.progress((i + 1) / total)
                    
                    data = all_data.get(symbol)
                    if data and vdb_service.is_data_complete(data):
                        db_hits += 1
                        score = ScoringService.calculate_score(data)
                        rec = ScoringService.get_recommendation(score)
                        
                        div_hist = data.dividend_history
                        results.append({
                            "Symbol": symbol,
                            "Company": (data.name or symbol)[:22],
                            "Sector": data.sector,
                            "Streak": div_hist.consecutive_years if div_hist else 0,
                            "Yield %": data.dividend_yield_pct,
                            "CAGR %": div_hist.cagr_5y if div_hist else None,
                            "Payout %": data.payout_ratio_pct,
                            "P/E": data.trailing_pe,
                            "Price": data.price,
                            "Score": score,
                            "Rec": rec.label,
                            "Source": "DB",
                            "_data": data,
                        })
                    else:
                        # Fetch from API for missing/incomplete
                        fallback_data = get_stock_data(symbol)
                        if fallback_data:
                            api_hits += 1
                            score = ScoringService.calculate_score(fallback_data)
                            rec = ScoringService.get_recommendation(score)
                            
                            div_hist = fallback_data.dividend_history
                            results.append({
                                "Symbol": symbol,
                                "Company": (fallback_data.name or symbol)[:22],
                                "Sector": fallback_data.sector,
                                "Streak": div_hist.consecutive_years if div_hist else 0,
                                "Yield %": fallback_data.dividend_yield_pct,
                                "CAGR %": div_hist.cagr_5y if div_hist else None,
                                "Payout %": fallback_data.payout_ratio_pct,
                                "P/E": fallback_data.trailing_pe,
                                "Price": fallback_data.price,
                                "Score": score,
                                "Rec": rec.label,
                                "Source": "API",
                                "_data": fallback_data,
                            })
            else:
                # VectorDB not populated, use API
                for i, symbol in enumerate(DIVIDEND_KINGS):
                    status.text(f"Fetching {symbol}... ({i + 1}/{total})")
                    progress.progress((i + 1) / total)
                    
                    data = get_stock_data(symbol)
                    if data:
                        api_hits += 1
                        score = ScoringService.calculate_score(data)
                        rec = ScoringService.get_recommendation(score)
                        
                        div_hist = data.dividend_history
                        results.append({
                            "Symbol": symbol,
                            "Company": (data.name or symbol)[:22],
                            "Sector": data.sector,
                            "Streak": div_hist.consecutive_years if div_hist else 0,
                            "Yield %": data.dividend_yield_pct,
                            "CAGR %": div_hist.cagr_5y if div_hist else None,
                            "Payout %": data.payout_ratio_pct,
                            "P/E": data.trailing_pe,
                            "Price": data.price,
                            "Score": score,
                            "Rec": rec.label,
                            "Source": "API",
                            "_data": data,
                        })
                    
                    time.sleep(API_DELAY_SECONDS)
        else:
            # Fallback: sequential API calls
            for i, symbol in enumerate(DIVIDEND_KINGS):
                status.text(f"Fetching {symbol} from API... ({i + 1}/{total})")
                progress.progress((i + 1) / total)
                
                data = get_stock_data(symbol)
                if data:
                    api_hits += 1
                    score = ScoringService.calculate_score(data)
                    rec = ScoringService.get_recommendation(score)
                    
                    div_hist = data.dividend_history
                    results.append({
                        "Symbol": symbol,
                        "Company": (data.name or symbol)[:22],
                        "Sector": data.sector,
                        "Streak": div_hist.consecutive_years if div_hist else 0,
                        "Yield %": data.dividend_yield_pct,
                        "CAGR %": div_hist.cagr_5y if div_hist else None,
                        "Payout %": data.payout_ratio_pct,
                        "P/E": data.trailing_pe,
                        "Price": data.price,
                        "Score": score,
                        "Rec": rec.label,
                        "Source": "API",
                        "_data": data,
                    })
                
                time.sleep(API_DELAY_SECONDS)
        
        progress.empty()
        status.empty()
        
        # Show source summary
        if db_hits > 0 or api_hits > 0:
            st.info(f"📊 Data sources: **{db_hits}** from Analysed stocks, **{api_hits}** from API")
        
        if results:
            return pd.DataFrame(results).sort_values("Score", ascending=False)
        return pd.DataFrame()
    
    @staticmethod
    def _render_summary(df: pd.DataFrame) -> None:
        """Render summary statistics."""
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Total Analyzed", len(df))
        with col2:
            avg_streak = df["Streak"].mean()
            st.metric("Avg Streak", f"{avg_streak:.0f} yrs")
        with col3:
            avg_yield = df["Yield %"].mean()
            st.metric("Avg Yield", f"{avg_yield:.2f}%")
        with col4:
            buys = len(df[df["Rec"].isin(["STRONG BUY", "BUY"])])
            st.metric("🟢 Buy/Strong Buy", buys)
        with col5:
            avoids = len(df[df["Rec"] == "AVOID"])
            st.metric("🔴 Avoid", avoids)
    
    @staticmethod
    def _render_top_picks(df: pd.DataFrame) -> None:
        """Render top recommendations with key metrics."""
        st.subheader("🏆 Top Picks")
        
        for _, row in df.head(5).iterrows():
            score = row["Score"]
            if score >= 80:
                emoji = "🟢"
            elif score >= 65:
                emoji = "🟡"
            else:
                emoji = "🟠"
            
            streak = f"{row['Streak']}yr" if row["Streak"] else "-"
            yld = UIComponents.format_percent(row["Yield %"]) if pd.notna(row["Yield %"]) else "-"
            cagr = UIComponents.format_percent(row["CAGR %"]) if pd.notna(row["CAGR %"]) else "-"
            
            st.markdown(
                f"{emoji} **{row['Symbol']}** ({row['Company']}) — "
                f"Score: **{score}** | Streak: {streak} | Yield: {yld} | Growth: {cagr}"
            )
    
    @staticmethod
    def _render_by_tier(df: pd.DataFrame) -> None:
        """Render stocks grouped by dividend tier."""
        st.subheader("👑 By Dividend Tier")
        
        # Kings (50+ years)
        kings = df[df["Streak"] >= 50].head(5)
        if not kings.empty:
            st.markdown("**Dividend Kings (50+ Years)**")
            for _, row in kings.iterrows():
                yld = UIComponents.format_percent(row["Yield %"]) if pd.notna(row["Yield %"]) else "-"
                st.markdown(f"👑 **{row['Symbol']}** — {row['Streak']} yrs | {yld} yield | Score: {row['Score']}")
        
        # Near-Kings (40-49 years)
        near_kings = df[(df["Streak"] >= 40) & (df["Streak"] < 50)].head(3)
        if not near_kings.empty:
            st.markdown("**Near Kings (40-49 Years)**")
            for _, row in near_kings.iterrows():
                st.markdown(f"🏆 **{row['Symbol']}** — {row['Streak']} yrs | Score: {row['Score']}")
    
    @staticmethod
    def _render_data_table(df: pd.DataFrame) -> None:
        """Render filterable data table."""
        st.subheader("📊 All Stocks")
        
        # Filters
        col1, col2 = st.columns(2)
        with col1:
            min_streak = st.slider("Min Dividend Streak (Years)", 0, 70, 25)
        with col2:
            min_yield = st.slider("Min Yield (%)", 0.0, 10.0, 0.0, 0.5)
        
        # Apply filters
        filtered = df[
            (df["Streak"] >= min_streak) & 
            (df["Yield %"].fillna(0) >= min_yield)
        ]
        
        display_cols = ["Symbol", "Company", "Streak", "Yield %", "CAGR %", "Payout %", "P/E", "Score", "Rec"]
        
        st.dataframe(
            filtered[display_cols],
            width="stretch",
            hide_index=True,
            column_config={
                "Streak": st.column_config.NumberColumn(format="%d yrs"),
                "Yield %": st.column_config.NumberColumn(format="%.2f%%"),
                "CAGR %": st.column_config.NumberColumn(format="%.1f%%"),
                "Payout %": st.column_config.NumberColumn(format="%.0f%%"),
                "P/E": st.column_config.NumberColumn(format="%.1f"),
                "Score": st.column_config.ProgressColumn(min_value=0, max_value=100),
            },
        )
        
        st.caption(f"Showing {len(filtered)} of {len(df)} stocks")
    
    @staticmethod
    def _render_stock_details(df: pd.DataFrame) -> None:
        """Render detailed view for selected stock."""
        with st.expander("📋 Stock Details"):
            selected = st.selectbox("Select stock", df["Symbol"].tolist())
            
            if not selected:
                return
            
            row = df[df["Symbol"] == selected].iloc[0]
            data: StockData = row["_data"]
            score: int = row["Score"]
            
            tier_badge = UIComponents.get_tier_badge(data.dividend_tier)
            st.markdown(f"### {tier_badge} {data.name} ({selected})")
            st.caption(f"{data.sector} • {data.industry}")
            
            # Prime metrics
            UIComponents.display_prime_metrics(data, score)
            
            # Tabs for details
            tabs = st.tabs(["Dividend", "Valuation", "Health", "Performance"])
            
            with tabs[0]:
                UIComponents.display_dividend_details(data)
            with tabs[1]:
                UIComponents.display_valuation_metrics(data)
            with tabs[2]:
                UIComponents.display_financial_health(data)
            with tabs[3]:
                UIComponents.display_performance(data)
    
    @staticmethod
    def _render_export(df: pd.DataFrame, analysis_time: datetime) -> None:
        """Render comprehensive export options."""
        st.subheader("📤 Export Reports")
        
        export_cols = [
            "Symbol", "Company", "Sector", "Streak", "Yield %", 
            "CAGR %", "Payout %", "P/E", "Price", "Score", "Rec",
        ]
        
        # Summary section
        st.markdown(f"**Analysis Summary:** {len(df)} stocks analyzed on {analysis_time.strftime('%Y-%m-%d %H:%M')}")
        
        # Export tabs
        tab1, tab2 = st.tabs(["📊 Full Analysis Export", "📄 Individual Stock Reports"])
        
        with tab1:
            st.markdown("**Export all analyzed stocks:**")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                csv = df[export_cols].to_csv(index=False)
                st.download_button(
                    "📥 CSV (All Stocks)",
                    csv,
                    f"dividend_kings_analysis_{analysis_time.strftime('%Y%m%d')}.csv",
                    "text/csv",
                    width="stretch",
                )
            
            with col2:
                # JSON export of all stocks
                import json
                json_data = df[export_cols].to_dict(orient="records")
                json_export = json.dumps({
                    "analysis_date": analysis_time.isoformat(),
                    "total_stocks": len(df),
                    "stocks": json_data,
                }, indent=2, default=str)
                
                st.download_button(
                    "📋 JSON (All Stocks)",
                    json_export,
                    f"dividend_kings_analysis_{analysis_time.strftime('%Y%m%d')}.json",
                    "application/json",
                    width="stretch",
                )
            
            with col3:
                # Top picks summary
                top_picks = df[df["Rec"].isin(["STRONG BUY", "BUY"])][export_cols]
                if not top_picks.empty:
                    csv_top = top_picks.to_csv(index=False)
                    st.download_button(
                        f"⭐ Top Picks ({len(top_picks)})",
                        csv_top,
                        f"top_picks_{analysis_time.strftime('%Y%m%d')}.csv",
                        "text/csv",
                        width="stretch",
                    )
                else:
                    st.button("⭐ Top Picks (0)", disabled=True, width="stretch")
        
        with tab2:
            if REPORTLAB_AVAILABLE:
                st.markdown("**Generate PDF research report for individual stock:**")
                
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    selected_for_pdf = st.selectbox(
                        "Select stock for PDF report:",
                        df["Symbol"].tolist(),
                        key="pdf_export_select",
                        format_func=lambda x: f"{x} - {df[df['Symbol']==x]['Company'].values[0]} (Score: {df[df['Symbol']==x]['Score'].values[0]})",
                    )
                
                with col2:
                    if selected_for_pdf:
                        row = df[df["Symbol"] == selected_for_pdf].iloc[0]
                        stock_data: StockData = row["_data"]
                        stock_score: int = row["Score"]
                        
                        pros, cons = ScoringService.get_investment_thesis(stock_data)
                        rec = ScoringService.get_recommendation(stock_score)
                        
                        # Generate PDF
                        try:
                            pdf_bytes = generate_stock_report(
                                stock=stock_data,
                                score=stock_score,
                                recommendation=rec.label,
                                pros=pros,
                                cons=cons,
                            )
                            
                            st.download_button(
                                label=f"📥 Download PDF",
                                data=pdf_bytes,
                                file_name=f"Research_{selected_for_pdf}_{analysis_time.strftime('%Y%m%d')}.pdf",
                                mime="application/pdf",
                                type="primary",
                                width="stretch",
                            )
                        except Exception as e:
                            st.error(f"Error: {e}")
                
                # Preview
                if selected_for_pdf:
                    st.markdown("---")
                    row = df[df["Symbol"] == selected_for_pdf].iloc[0]
                    st.markdown(f"""
                    **Report Preview for {selected_for_pdf}:**
                    - Company: {row['Company']}
                    - Score: {row['Score']}/100 ({row['Rec']})
                    - Dividend Streak: {row['Streak']} years
                    - Yield: {row['Yield %']:.2f}%
                    """)
            else:
                st.info("📄 Install `reportlab` to enable PDF report generation: `pip install reportlab`")
    
    @staticmethod
    def _render_empty_state() -> None:
        """Render empty state."""
        st.info("👈 Click **Run Full Analysis** to analyze all Dividend Kings")
        
        st.markdown("""
        ### About This Analysis
        
        This tool analyzes all **Dividend Kings** — companies with 50+ consecutive 
        years of dividend increases. For each stock, we evaluate:
        
        | Factor | Why It Matters |
        |--------|----------------|
        | **Dividend Streak** | Longer = more reliable income |
        | **Yield** | Current income potential |
        | **Dividend Growth** | Future income growth |
        | **Payout Ratio** | Dividend sustainability |
        | **Valuation** | Entry point attractiveness |
        | **Financial Health** | Ability to maintain dividends |
        
        The analysis takes 2-3 minutes to complete.
        """)
    
    @classmethod
    def render(cls) -> None:
        """Render the full analysis view."""
        st.sidebar.markdown("---")
        st.sidebar.info(f"Analyzes {len(DIVIDEND_KINGS)} Dividend Kings (2-3 min)")
        
        if st.sidebar.button("Run Full Analysis", type="primary"):
            df = cls._run_analysis()
            if not df.empty:
                st.session_state["analysis_df"] = df
                st.session_state["analysis_time"] = datetime.now()
        
        if "analysis_df" not in st.session_state:
            cls._render_empty_state()
            return
        
        df: pd.DataFrame = st.session_state["analysis_df"]
        analysis_time: datetime = st.session_state["analysis_time"]
        
        st.caption(f"Analysis completed {analysis_time.strftime('%Y-%m-%d %H:%M')}")
        
        cls._render_summary(df)
        st.divider()
        
        cls._render_top_picks(df)
        st.divider()
        
        with st.expander("👑 View by Tier"):
            cls._render_by_tier(df)
        
        st.divider()
        cls._render_data_table(df)
        st.divider()
        cls._render_stock_details(df)
        st.divider()
        cls._render_export(df, analysis_time)
        
        # Footer with data source info
        if USE_ENHANCED_SERVICE:
            status = get_service_status()
            doc_count = status.get("document_count", 0)
            kings_count = status.get("dividend_kings", 0)
            if status.get("is_db_primary"):
                st.caption(f"🗄️ Analysed stocks: {doc_count} stocks ({kings_count} Kings) • Fast local data")
            else:
                st.caption("🌐 Public API • Run `python ingest_data.py --enrich` to populate local DB")
        else:
            st.caption(f"🌐 Data: {DATA_SOURCES['primary']} (API only)")
