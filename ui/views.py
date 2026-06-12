"""
Page views for the Streamlit application.

This module contains the main view classes optimized for dividend investors,
with key metrics prominently displayed on the first page.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, cast

import streamlit as st

from config import DATA_SOURCES
from data_ingestion.models import StockDocument
from models.stock import StockData
from services.scoring import Recommendation, ScoringService
from services.sector_service import SectorService
from services.stock_service import StockService
from ui.components import UIComponents

logger = logging.getLogger(__name__)

# Try to import Analysed-stocks-first service (primary data source)
try:
    from services.vectordb_service import get_vectordb_service

    VECTORDB_SERVICE_AVAILABLE = True
except ImportError:
    VECTORDB_SERVICE_AVAILABLE = False

# Try to import enhanced service (fallback with API calls)
try:
    from services.enhanced_stock_service import EnhancedStockService

    ENHANCED_SERVICE_AVAILABLE = True
except ImportError:
    ENHANCED_SERVICE_AVAILABLE = False


def get_stock_data(symbol: str) -> StockData | None:
    """
    Load stock data for single-stock analysis.

    Uses the shared library first, then falls back to enhanced or basic API services.
    """
    from services.stock_analysis_service import load_stock_data

    data = load_stock_data(
        symbol,
        include_yield_channel=False,
        fetch_realtime_prices=True,
    )
    if data is not None:
        return data

    if ENHANCED_SERVICE_AVAILABLE:
        from services.live_price import apply_live_price

        data = EnhancedStockService(fetch_realtime_prices=True).fetch(symbol)
        if data:
            return cast(StockData, apply_live_price(data))

    from services.live_price import apply_live_price

    data = StockService.fetch(symbol)
    return cast(StockData, apply_live_price(data)) if data else None


def get_service_status() -> dict[str, Any]:
    """Get status of the stock service."""
    status = {
        "mode": "API-only",
        "vector_db_available": False,
        "is_db_primary": False,
        "document_count": 0,
        "dividend_kings": 0,
    }

    try:
        from services.shared_market_db import shared_market_db_status

        market = shared_market_db_status()
        doc_count = int(market.get("document_count") or 0)
        if doc_count > 0:
            status["mode"] = "Analysed-stocks-first"
            status["vector_db_available"] = True
            status["is_db_primary"] = True
            status["document_count"] = doc_count
            status["sp500_coverage"] = market.get("sp500_coverage")
            return status
    except Exception as exc:
        logger.debug("shared_market_db_status lookup failed: %s", exc)

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
        except Exception as exc:
            logger.debug("get_vectordb_service failed: %s", exc)

    if ENHANCED_SERVICE_AVAILABLE and status["mode"] == "API-only":
        status["mode"] = "Enhanced (API + DB)"

    return status


USE_ENHANCED_SERVICE = ENHANCED_SERVICE_AVAILABLE or VECTORDB_SERVICE_AVAILABLE

# Try to import PDF report generator
try:
    from services.report_generator import generate_stock_report

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


class SingleStockView:
    """Full-page analysis for one symbol (portfolio holdings or S&P research)."""

    @staticmethod
    def _render_header(data: StockData, rec: Recommendation) -> None:
        """Company title only — score and figures live in Key highlights."""
        del rec  # shown in display_key_highlights
        tier_badge = UIComponents.get_tier_badge(data.dividend_tier)
        streak = data.dividend_history.consecutive_years if data.dividend_history else 0
        st.header(f"{tier_badge} {data.name}")
        st.caption(
            f"**{data.symbol}** · {data.sector} · {streak} years of consecutive dividend growth"
        )

    @classmethod
    def render(cls) -> None:
        """Render the single-stock selection and analysis view."""
        st.subheader("Analyze a stock")
        st.markdown(
            "Enter any US stock ticker symbol (e.g., KO, JNJ, PG, AAPL, MSFT) "
            "to load its dividend yield channel, scoring card, and key metrics."
        )
        symbol = (
            st.text_input("Ticker symbol", value="KO", key="single_stock_search_input")
            .strip()
            .upper()
        )
        if symbol:
            cls.render_analysis_for_symbol(symbol)

    @classmethod
    def render_analysis_for_symbol(
        cls,
        symbol: str,
        *,
        show_sector: bool = True,
        data: StockData | None = None,
        yield_channel_data: Any | None = None,
        vector_doc: StockDocument | None = None,
    ) -> None:
        """Render the full single-stock dashboard for a symbol."""
        if data is None:
            with st.spinner(f"Loading data for {symbol}..."):
                data = get_stock_data(symbol)
        else:
            from services.live_price import apply_live_price

            data = apply_live_price(data)

        if not data:
            st.error(f"Could not fetch data for {symbol}. Please verify the symbol.")
            return

        score = ScoringService.calculate_score(data)
        confidence = data.data_quality_score or 100
        rec = ScoringService.get_recommendation(score, confidence)
        pros, cons = ScoringService.get_investment_thesis(data)

        cls._render_header(data, rec)

        st.subheader("Key highlights")
        UIComponents.display_recommendation(rec.label, score, confidence)
        UIComponents.display_prime_metrics(data, score)

        st.divider()
        UIComponents.display_yield_channel_chart(
            symbol,
            years=10,
            channel_data=yield_channel_data,
            vector_doc=vector_doc,
            show_header=True,
        )

        st.divider()
        st.subheader("Investment view")
        UIComponents.display_investment_thesis(pros, cons)

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

        with st.expander("More metrics", expanded=False):
            UIComponents.display_dividend_details(data)
            st.divider()
            UIComponents.display_valuation_metrics(data)
            st.divider()
            UIComponents.display_financial_health(data)
            st.divider()
            UIComponents.display_profitability(data)
            st.divider()
            UIComponents.display_performance(data)

        with st.expander("News & sentiment", expanded=False):
            UIComponents.display_news_summary(symbol, days=7)

        if show_sector and data.sector != "N/A":
            with st.expander("Sector comparison", expanded=False):
                with st.spinner(f"Loading {data.sector} peers…"):
                    sector_peers, external = SectorService.get_top_sector_peers(
                        data, score, include_external=True
                    )
                UIComponents.display_sector_comparison(
                    data,
                    score,
                    sector_peers,
                    external,
                    _yield_channels={symbol.upper(): yield_channel_data}
                    if yield_channel_data
                    else None,
                    _vector_docs={symbol.upper(): vector_doc} if vector_doc else None,
                )

        with st.expander("Data sources & library record", expanded=False):
            UIComponents.display_vector_db_data(
                symbol,
                document=vector_doc,
            )

        st.divider()
        cls._render_report_section(data, score, rec, pros, cons, symbol)

        st.divider()
        cls._render_data_source_footer(data, confidence, symbol=symbol, vector_doc=vector_doc)

    @classmethod
    def _render_report_section(
        cls,
        data: StockData,
        score: int,
        rec: Recommendation,
        pros: list[str],
        cons: list[str],
        symbol: str,
    ) -> None:
        """Render the report generation and export section."""
        st.subheader("📄 Research Report")

        sector_txt = data.sector if data.sector and data.sector != "N/A" else "—"
        streak = data.dividend_history.consecutive_years if data.dividend_history else 0
        yield_txt = (
            f"{data.dividend_yield_pct:.2f}%" if data.dividend_yield_pct is not None else "—"
        )
        payout_txt = (
            f"{data.payout_ratio_pct:.0f}% of earnings"
            if data.payout_ratio_pct is not None
            else "—"
        )

        # Report preview in a styled container
        generated_date = datetime.now().strftime("%B %d, %Y")
        with st.container():
            st.markdown(
                f"""
                <div style="border: 1px solid #ddd; border-radius: 8px; padding: 16px;
                            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);">
                    <h4 style="margin: 0 0 8px 0; color: #1a237e;">
                        📊 {data.name} ({symbol}) - Research Report
                    </h4>
                    <p style="color: #666; margin: 0 0 12px 0;">
                        {data.dividend_tier} | {sector_txt} | Generated {generated_date}
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
            st.markdown("**Key Highlights:**")
            st.markdown(f"""
            - **Score:** {score}/100 ({rec.label})
            - **Yield:** {yield_txt}
            - **Streak:** {streak} years
            - **Payout:** {payout_txt}
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
        pros: list[str],
        cons: list[str],
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
        writer.writerow(
            [
                "Dividend Yield",
                f"{data.dividend_yield_pct:.2f}%" if data.dividend_yield_pct else "N/A",
            ]
        )
        writer.writerow(
            [
                "Annual Dividend",
                f"${data.dividend_rate:.2f}" if data.dividend_rate else "N/A",
            ]
        )

        dh = data.dividend_history
        writer.writerow(["Consecutive Years", dh.consecutive_years if dh else "N/A"])
        writer.writerow(["5Y Div CAGR", f"{dh.cagr_5y:.2f}%" if dh and dh.cagr_5y else "N/A"])
        writer.writerow(["10Y Div CAGR", f"{dh.cagr_10y:.2f}%" if dh and dh.cagr_10y else "N/A"])
        writer.writerow([])

        # Safety
        writer.writerow(["=== DIVIDEND SAFETY ===", ""])
        writer.writerow(
            [
                "Payout Ratio",
                f"{data.payout_ratio_pct:.1f}%" if data.payout_ratio_pct else "N/A",
            ]
        )
        writer.writerow(
            [
                "FCF Payout",
                f"{data.fcf_payout_ratio_pct:.1f}%" if data.fcf_payout_ratio_pct else "N/A",
            ]
        )
        writer.writerow(
            [
                "Dividend Coverage",
                f"{data.dividend_coverage:.2f}x" if data.dividend_coverage else "N/A",
            ]
        )
        writer.writerow([])

        # Valuation
        writer.writerow(["=== VALUATION ===", ""])
        writer.writerow(["P/E Ratio", f"{data.trailing_pe:.2f}" if data.trailing_pe else "N/A"])
        writer.writerow(["Forward P/E", f"{data.forward_pe:.2f}" if data.forward_pe else "N/A"])
        writer.writerow(
            ["Price/Book", f"{data.price_to_book:.2f}" if data.price_to_book else "N/A"]
        )
        writer.writerow(
            [
                "Market Cap",
                f"${data.market_cap / 1e9:.2f}B" if data.market_cap else "N/A",
            ]
        )
        writer.writerow([])

        # Financial Health
        writer.writerow(["=== FINANCIAL HEALTH ===", ""])
        writer.writerow(
            [
                "Debt/Equity",
                f"{data.debt_to_equity:.2f}" if data.debt_to_equity else "N/A",
            ]
        )
        writer.writerow(
            [
                "Current Ratio",
                f"{data.current_ratio:.2f}" if data.current_ratio else "N/A",
            ]
        )
        writer.writerow(["ROE", f"{data.roe_pct:.2f}%" if data.roe_pct else "N/A"])
        writer.writerow(
            [
                "Operating Margin",
                f"{data.operating_margin_pct:.2f}%" if data.operating_margin_pct else "N/A",
            ]
        )
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
        pros: list[str],
        cons: list[str],
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
        _confidence: float,
        *,
        symbol: str = "",
        vector_doc: StockDocument | None = None,
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


class PortfolioView:
    """Wrapper view to render the portfolio details table, avoiding circular imports."""

    @classmethod
    def render(cls) -> None:
        from ui.portfolio_details_view import PortfolioDetailsView

        PortfolioDetailsView.render()


class FullAnalysisView:
    """View to run and show full analysis for all Dividend Kings/Aristocrats."""

    @classmethod
    def render(cls) -> None:
        st.subheader("All Dividend Kings Analysis")
        st.markdown(
            "Analyze and rank the entire universe of elite dividend stocks. "
            "Filter by dividend streak or yield to discover high-quality income opportunities."
        )

        import pandas as pd

        from config import DIVIDEND_KINGS
        from services.vectordb_service import get_vectordb_service

        db_service = get_vectordb_service()
        symbols = DIVIDEND_KINGS

        if st.button("Run Full Analysis", type="primary", key="run_full_analysis_btn"):
            with st.spinner("Analyzing all stocks... This may take a few moments..."):
                results = []
                for symbol in symbols:
                    data = db_service.get_stock(symbol)
                    if not data:
                        data = get_stock_data(symbol)
                    if data:
                        score = ScoringService.calculate_score(data)
                        results.append(
                            {
                                "Ticker": data.symbol,
                                "Company": data.name,
                                "Sector": data.sector,
                                "Score": score,
                                "Yield %": data.dividend_yield_pct or 0.0,
                                "Streak (Yrs)": data.dividend_history.consecutive_years
                                if data.dividend_history
                                else 0,
                                "Payout %": data.payout_ratio_pct or 0.0,
                                "P/E": data.trailing_pe or 0.0,
                            }
                        )
                st.session_state["full_analysis_results"] = results

        results = st.session_state.get("full_analysis_results")
        if results:
            df = pd.DataFrame(results)

            # Filters
            col1, col2 = st.columns(2)
            with col1:
                min_streak = st.slider("Min Streak (Years)", min_value=0, max_value=100, value=50)
            with col2:
                min_yield = st.slider(
                    "Min Yield %", min_value=0.0, max_value=10.0, value=0.0, step=0.5
                )

            filtered_df = df[(df["Streak (Yrs)"] >= min_streak) & (df["Yield %"] >= min_yield)]

            st.markdown(f"### Results ({len(filtered_df)} stocks found)")
            st.dataframe(
                filtered_df,
                use_container_width=True,
                hide_index=True,
            )

            # Export
            csv = filtered_df.to_csv(index=False)
            st.download_button(
                "Export CSV",
                csv,
                "dividend_kings_analysis.csv",
                "text/csv",
                key="export_full_analysis_csv",
            )
