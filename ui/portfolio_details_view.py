"""
Portfolio details page for the Streamlit application.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from models.stock import StockData
from services.portfolio_analysis_preload import PortfolioAnalysisPreload
from services.portfolio_details_service import PortfolioDetailRow, PortfolioDetailsService
from services.portfolio_zone_overview import (
    ZONE_CATEGORY_META,
    build_zone_dataframe,
    create_category_count_chart,
    create_position_zone_chart,
    summarize_categories,
    tickers_missing_zones,
)
from services.portfolio_dividend_calendar import (
    build_portfolio_dividend_calendar,
    create_month_comparison_chart,
    create_month_payers_chart,
)
from data_ingestion.portfolio_store import PortfolioStore
from services.portfolio_deposits_service import PortfolioDepositsService
from services.portfolio_dashboard_service import PortfolioDashboardService
from services.portfolio_allocation_service import PortfolioAllocationService
from data_ingestion.deposits_store import MonthlyDeposit
from services.portfolio_benchmark_service import PortfolioBenchmarkService
from services.portfolio_dividend_income_service import PortfolioDividendIncomeService
from services.portfolio_purchase_journal_service import PortfolioPurchaseJournalService
from services.portfolio_dividend_growth_service import (
    SINCE_YEAR,
    PortfolioDividendGrowthService,
)
from services.portfolio_attention_service import (
    PortfolioAttentionService,
    normalize_attention_summary,
)
from ui.dividend_timing_display import dividend_timing_legend, render_dividend_timing_dataframe
from ui.portfolio_manage_panel import render_tab_refresh_button
from services.dividend_timing import classify_dividend_timing
from ui.portfolio_risk_panel import SESSION_SUMMARY_KEY, get_cached_attention_summary
from services.portfolio_holding_detail_service import PortfolioHoldingDetailService
from data_ingestion.sp500_universe import sectors_match
from services.scoring import ScoringService
from ui.views import SingleStockView
from ui.components import UIComponents
from utils.formatting import format_large_number
from ui.charts import show_chart
from ui.theme import (
    PORTFOLIO_TAB_SCOPES,
    pick_portfolio_section,
    portfolio_data_ready,
    render_portfolio_status_line,
)

PORTFOLIO_VIEW_OVERVIEW = "overview"
PORTFOLIO_VIEW_HOLDING = "holding"


def _set_holding_selection(symbol: str, nav_tickers: Optional[List[str]] = None) -> None:
    """Switch to full-page holding analysis for the chosen symbol."""
    from ui.portfolio_home import set_holding_selection

    set_holding_selection(symbol, nav_tickers=nav_tickers)


@st.cache_data(ttl=3600, show_spinner="Loading benchmark index prices…")
def _load_benchmark_comparison() -> pd.DataFrame:
    return PortfolioBenchmarkService().build_comparison_dataframe()


@st.cache_data(ttl=3600, show_spinner="Loading dividend history for portfolio…")
def _load_dividend_growth():
    return PortfolioDividendGrowthService().build_symbol_growth()


def _load_portfolio_payload(
    *,
    use_live_prices: bool = True,
) -> tuple[List[PortfolioDetailRow], PortfolioAnalysisPreload]:
    """Load holdings table + analysis preload (stored in session_state)."""
    return PortfolioDetailsService().build_rows_with_cache(use_live_prices=use_live_prices)


def _preload_from_session() -> PortfolioAnalysisPreload:
    return PortfolioAnalysisPreload(
        stock_data=st.session_state.get("portfolio_stock_cache", {}),
        yield_channels=st.session_state.get("portfolio_yield_cache", {}),
        vector_docs=st.session_state.get("portfolio_vector_docs", {}),
    )


def _ensure_yield_preload_if_needed() -> None:
    """Load yield-channel charts after a fast library-only portfolio open."""
    if not st.session_state.get("portfolio_fast_loaded"):
        return
    from services.portfolio_ui_cache import ensure_portfolio_yield_preload

    with st.spinner("Loading yield charts…"):
        ensure_portfolio_yield_preload()


class PortfolioDetailsView:
    """Render the full portfolio details table."""

    @staticmethod
    def _render_tab_header(tab_key: str, *, show_refresh: bool = False) -> None:
        title, _scope = PORTFOLIO_TAB_SCOPES[tab_key]
        if show_refresh:
            col_title, col_refresh = st.columns([6, 1])
            with col_title:
                st.subheader(title)
            with col_refresh:
                render_tab_refresh_button(tab_key)
        else:
            st.subheader(title)

    @staticmethod
    def _rows_to_dataframe(
        rows: List[PortfolioDetailRow],
        preload: Optional[PortfolioAnalysisPreload] = None,
    ) -> pd.DataFrame:
        yield_channels = preload.yield_channels if preload else {}

        def _zone_label(ticker: str) -> str:
            channel = yield_channels.get(ticker)
            if not channel:
                return "—"
            from services.portfolio_zone_overview import zone_to_category

            key = zone_to_category(channel.zone)
            meta = ZONE_CATEGORY_META[key]
            return f"{meta['emoji']} {meta['short']} ({channel.zone})"

        return pd.DataFrame(
            [
                {
                    "Yield Zone": _zone_label(row.ticker),
                    "Company": row.company,
                    "Ticker": row.ticker,
                    "Market CAP": format_large_number(row.market_cap).replace("$", "")
                    if row.market_cap is not None
                    else "N/A",
                    "P/E Ratio": row.pe_ratio,
                    "Shares": row.shares,
                    "Current Price": row.current_price,
                    "Current Value": row.current_value,
                    "Avg Cost/Share": row.avg_cost_per_share,
                    "Acquisition Value": row.acquisition_value,
                    "Profit": row.profit,
                    "Profit %": row.profit_pct,
                    "Est. Avg Price": row.estimated_avg_price,
                    "Medium Price Last 365 Days": row.medium_price_365d,
                    "180 Day Price": row.price_180d,
                    "365 Day Price": row.price_365d,
                    "180": row.change_180d_pct,
                    "365 Day %": row.change_365d_pct,
                    "Weight %": row.weight_pct,
                    "Div Yield %": row.dividend_yield_pct,
                    "Div/Share": row.dividend_per_share,
                    "Income/Year": row.annual_income,
                    "Div Weight %": row.dividend_weight_pct,
                    "Income Weight %": row.income_weight_pct,
                    "Div Paid": row.dividends_paid,
                    "Growth Years": row.growth_years,
                    "Commission": row.commission,
                    "Sector": row.sector,
                    "% of Total Acquisitions": row.acquisition_share_pct,
                    "Evaluare Analisti": row.analyst_rating,
                    "P/FCF": row.price_to_fcf,
                    "Compute Dividend": row.computed_dividend,
                    "Ex Dividend Date": row.ex_dividend_date,
                    "Dividend Pay Date": row.dividend_pay_date,
                    "Data Source": row.data_source,
                }
                for row in rows
            ]
        )

    @classmethod
    def _render_portfolio_hero(cls, rows: List[PortfolioDetailRow]) -> None:
        """Compact KPI strip shown above all portfolio sections."""
        total_value = sum(row.current_value or 0.0 for row in rows)
        total_acquisition = sum(row.acquisition_value for row in rows)
        total_profit = total_value - total_acquisition
        profit_pct = (total_profit / total_acquisition * 100) if total_acquisition else None
        total_income = sum(row.annual_income or 0.0 for row in rows)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Positions", len(rows))
        c2.metric("Portfolio value", f"${total_value:,.0f}")
        c3.metric(
            "Total P/L",
            f"${total_profit:+,.0f}",
            f"{profit_pct:+.1f}%" if profit_pct is not None else None,
        )
        c4.metric("Annual income", f"${total_income:,.0f}")
        c5.metric(
            "Avg yield",
            f"{(total_income / total_value * 100):.2f}%"
            if total_value
            else "—",
        )

    @classmethod
    def _render_quick_holdings(cls, rows: List[PortfolioDetailRow]) -> None:
        """Top holdings as one-click shortcuts into full analysis."""
        ranked = sorted(
            rows,
            key=lambda row: row.current_value or 0.0,
            reverse=True,
        )[:10]
        if not ranked:
            return

        st.markdown("##### Quick open")
        st.caption("Tap a position to open its full dividend analysis page.")
        cols = st.columns(5)
        for index, row in enumerate(ranked):
            label = row.ticker
            value = row.current_value or 0.0
            profit = row.profit_pct
            hint = f"${value:,.0f}"
            if profit is not None:
                hint += f" · {profit:+.1f}%"
            with cols[index % 5]:
                if st.button(
                    label,
                    help=hint,
                    key=f"portfolio_quick_{row.ticker}",
                    use_container_width=True,
                ):
                    _set_holding_selection(
                        row.ticker,
                        nav_tickers=[item.ticker for item in ranked],
                    )

    @staticmethod
    def _render_summary(rows: List[PortfolioDetailRow]) -> None:
        total_value = sum(row.current_value or 0.0 for row in rows)
        total_acquisition = sum(row.acquisition_value for row in rows)
        total_profit = total_value - total_acquisition
        total_income = sum(row.annual_income or 0.0 for row in rows)
        total_dividends_paid = sum(row.dividends_paid for row in rows)

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Positions", len(rows))
        with col2:
            st.metric("Current Value", f"${total_value:,.2f}")
        with col3:
            st.metric("Acquisition Value", f"${total_acquisition:,.2f}")
        with col4:
            profit_pct = (total_profit / total_acquisition * 100) if total_acquisition else None
            st.metric(
                "Total Profit",
                f"${total_profit:,.2f}",
                f"{profit_pct:+.2f}%" if profit_pct is not None else None,
            )
        with col5:
            st.metric("Annual Dividend Income", f"${total_income:,.2f}")
        st.caption(f"Lifetime dividends received: ${total_dividends_paid:,.2f}")

    @staticmethod
    def _render_filters(df: pd.DataFrame) -> pd.DataFrame:
        col1, col2, col3 = st.columns(3)
        with col1:
            sectors = sorted(df["Sector"].dropna().unique().tolist())
            selected_sectors = st.multiselect("Sector", sectors, default=sectors)
        with col2:
            tickers = sorted(df["Ticker"].dropna().unique().tolist())
            selected_tickers = st.multiselect("Ticker", tickers, default=tickers)
        with col3:
            search = st.text_input("Search company or ticker")

        filtered = df[
            df["Sector"].isin(selected_sectors) & df["Ticker"].isin(selected_tickers)
        ]
        if search:
            needle = search.strip().lower()
            filtered = filtered[
                filtered["Company"].str.lower().str.contains(needle, na=False)
                | filtered["Ticker"].str.lower().str.contains(needle, na=False)
            ]
        return filtered

    @staticmethod
    def _label_for_symbol(rows: List[PortfolioDetailRow], symbol: str) -> str:
        for row in rows:
            if row.ticker == symbol:
                return f"{row.ticker} — {row.company}"
        return symbol

    @classmethod
    def _render_monthly_dividend_exposure(
        cls,
        rows: List[PortfolioDetailRow],
        preload: PortfolioAnalysisPreload,
    ) -> None:
        """Monthly dividend cash forecast and payer chart with drill-down."""
        holdings = PortfolioStore().list_holdings()
        if not holdings:
            return

        row_dates = {
            row.ticker: (row.ex_dividend_date, row.dividend_pay_date)
            for row in rows
        }
        calendar = build_portfolio_dividend_calendar(
            holdings,
            vector_docs=preload.vector_docs,
            stock_data=preload.stock_data,
            row_dates=row_dates,
        )
        current = calendar.current_month
        last = calendar.last_month
        next_month = calendar.next_month

        st.caption(
            "Last month uses **actual dividend payments** recorded in analysed stocks "
            "(cash date in that month). This month and next month add scheduled and projected "
            "payments from announced dates and usual payment patterns."
        )

        delta_vs_last = current.total_cash - last.total_cash
        delta_vs_next = next_month.total_cash - current.total_cash

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                f"This month ({current.label})",
                f"${current.total_cash:,.2f}",
                f"{current.payer_count} payers",
            )
        with col2:
            st.metric(
                f"Last month ({last.label})",
                f"${last.total_cash:,.2f}",
                f"{last.payer_count} payers · actual",
            )
        with col3:
            st.metric(
                f"Next month ({next_month.label})",
                f"${next_month.total_cash:,.2f}",
                f"${delta_vs_next:+,.0f} vs this month",
                delta_color="normal" if delta_vs_next >= 0 else "inverse",
            )
        with col4:
            annualized = (current.total_cash * 12) if current.total_cash else 0
            st.metric("Run-rate (×12)", f"${annualized:,.2f}")

        comparison = create_month_comparison_chart(calendar)
        if comparison:
            show_chart(comparison, width="stretch", key="portfolio_monthly_comparison")

        payers_chart = create_month_payers_chart(current)
        if payers_chart:
            show_chart(payers_chart, width="stretch", key="portfolio_monthly_payers")
        elif current.payer_count == 0:
            st.info("No dividend payments expected this month based on available history.")

        st.markdown(f"#### Paying this month ({current.label})")
        dividend_timing_legend()
        if not current.holdings:
            st.caption("No holdings matched the current-month dividend schedule.")
        else:
            today = calendar.reference_date
            payer_rows = []
            for item in current.holdings:
                payer_rows.append(
                    {
                        "Ticker": item.symbol,
                        "Company": item.company,
                        "Timing": classify_dividend_timing(
                            today=today,
                            ex_date=item.ex_date,
                            pay_date=item.payment_date,
                            status=item.status,
                        ),
                        "Ex-Date": item.ex_date,
                        "Pay Date": item.payment_date,
                        "Per Share": item.per_share,
                        "Shares": item.shares,
                        "Expected Cash": item.expected_cash,
                    }
                )
            payer_df = pd.DataFrame(payer_rows)
            payer_selection = render_dividend_timing_dataframe(
                payer_df,
                table_key="portfolio_monthly_payer_table",
            )
            selected = getattr(getattr(payer_selection, "selection", None), "rows", None)
            if selected:
                _set_holding_selection(
                    payer_df.iloc[selected[0]]["Ticker"],
                    nav_tickers=[item.symbol for item in current.holdings],
                )

        with st.expander(f"Last month detail — {last.label} (actual received)"):
            if not last.holdings:
                st.write("No dividend payments recorded for this month in the database.")
            else:
                detail = pd.DataFrame(
                    [
                        {
                            "Ticker": item.symbol,
                            "Company": item.company,
                            "Timing": classify_dividend_timing(
                                today=calendar.reference_date,
                                ex_date=item.ex_date,
                                pay_date=item.payment_date,
                                status="received",
                            ),
                            "Pay Date": item.payment_date,
                            "Per Share": item.per_share,
                            "Shares": item.shares,
                            "Received": item.expected_cash,
                        }
                        for item in last.holdings
                    ]
                )
                render_dividend_timing_dataframe(
                    detail,
                    table_key="portfolio_last_month_dividends",
                    on_select=False,
                )

        with st.expander(f"Next month detail — {next_month.label} (expected)"):
            if not next_month.holdings:
                st.write("No expected payers.")
            else:
                detail = pd.DataFrame(
                    [
                        {
                            "Ticker": item.symbol,
                            "Company": item.company,
                            "Timing": classify_dividend_timing(
                                today=calendar.reference_date,
                                ex_date=item.ex_date,
                                pay_date=item.payment_date,
                                status=item.status,
                            ),
                            "Expected Cash": item.expected_cash,
                            "Ex-Date": item.ex_date,
                            "Pay Date": item.payment_date,
                        }
                        for item in next_month.holdings
                    ]
                )
                render_dividend_timing_dataframe(
                    detail,
                    table_key="portfolio_next_month_dividends",
                    on_select=False,
                )

    @classmethod
    def _render_zone_overview(
        cls,
        rows: List[PortfolioDetailRow],
        preload: PortfolioAnalysisPreload,
        filtered_tickers: List[str],
    ) -> None:
        """Green / yellow / red yield-zone chart with drill-down into holding analysis."""
        if not st.session_state.get("portfolio_analysis_ready"):
            return

        visible = [row for row in rows if row.ticker in filtered_tickers]
        labels = {row.ticker: row.company for row in visible}
        weights = {
            row.ticker: row.weight_pct
            for row in visible
            if row.weight_pct is not None
        }
        channels = {
            ticker: preload.yield_channels[ticker]
            for ticker in filtered_tickers
            if ticker in preload.yield_channels
        }
        zone_df = build_zone_dataframe(channels, labels=labels, weights=weights)

        st.markdown("##### Yield zone map")
        st.caption(
            "Based on Geraldine Weiss dividend yield channels: "
            "**green** = buy zone (yield above history), "
            "**yellow** = fair value, "
            "**red** = caution or expensive. "
            "Click a chart point or table row to open full-page holding analysis."
        )

        if zone_df.empty:
            missing = tickers_missing_zones(filtered_tickers, preload.yield_channels)
            st.warning(
                "No yield-channel data for the current selection. "
                f"Missing: {', '.join(missing[:12])}"
                + ("…" if len(missing) > 12 else "")
            )
            return

        counts = summarize_categories(zone_df)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric(
                f"{ZONE_CATEGORY_META['green']['emoji']} Green",
                counts["green"],
                help="Deep Value or Value — yield above historical norms",
            )
        with c2:
            st.metric(
                f"{ZONE_CATEGORY_META['yellow']['emoji']} Yellow",
                counts["yellow"],
                help="Fair Value — yield near long-term median",
            )
        with c3:
            st.metric(
                f"{ZONE_CATEGORY_META['red']['emoji']} Red",
                counts["red"],
                help="Caution or Expensive — yield below historical norms",
            )
        with c4:
            st.metric("Analyzed", len(zone_df), help="Holdings with yield-channel data")

        category_options = ["Green", "Yellow", "Red"]
        default_categories = st.session_state.get(
            "portfolio_zone_filter",
            category_options,
        )
        selected_categories = st.multiselect(
            "Filter by zone color",
            category_options,
            default=[c for c in default_categories if c in category_options]
            or category_options,
            key="portfolio_zone_filter_select",
        )
        st.session_state["portfolio_zone_filter"] = selected_categories

        display_df = zone_df[zone_df["Category"].isin(selected_categories)]
        if display_df.empty:
            st.info("No holdings match the selected zone colors.")
            return

        chart_left, chart_right = st.columns([1, 2])
        with chart_left:
            pie = create_category_count_chart(display_df)
            if pie:
                pie_event = show_chart(
                    pie,
                    width="stretch",
                    key="portfolio_zone_pie",
                    on_select="rerun",
                    selection_mode="points",
                )
                cls._apply_plotly_zone_selection(pie_event, display_df)
        with chart_right:
            bar = create_position_zone_chart(display_df)
            if bar:
                bar_event = show_chart(
                    bar,
                    width="stretch",
                    key="portfolio_zone_bar",
                    on_select="rerun",
                    selection_mode="points",
                )
                cls._apply_plotly_zone_selection(bar_event, display_df)

        st.markdown("#### Holdings by zone — select to drill down")
        zone_table = display_df[
            [
                "Ticker",
                "Company",
                "Category",
                "Zone",
                "Current Yield %",
                "Median Yield %",
                "Percentile",
                "Gap to Fair %",
                "Portfolio Weight %",
            ]
        ].copy()
        zone_table["Gap to Fair %"] = zone_table["Gap to Fair %"].map(
            lambda value: f"{value:+.1f}%" if pd.notna(value) else "N/A"
        )
        zone_table["Portfolio Weight %"] = zone_table["Portfolio Weight %"].map(
            lambda value: f"{value:.2f}%" if pd.notna(value) else "N/A"
        )

        zone_selection = st.dataframe(
            zone_table,
            width="stretch",
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="portfolio_zone_table",
        )
        zone_rows = getattr(getattr(zone_selection, "selection", None), "rows", None)
        if zone_rows:
            ticker = display_df.iloc[zone_rows[0]]["Ticker"]
            _set_holding_selection(ticker, nav_tickers=display_df["Ticker"].tolist())

    @staticmethod
    def _apply_plotly_zone_selection(event: Any, zone_df: pd.DataFrame) -> None:
        """Set drill-down ticker from a plotly chart click."""
        if event is None or zone_df.empty:
            return
        selection = getattr(event, "selection", None)
        if not selection:
            return
        points = getattr(selection, "points", None) or selection.get("points", [])
        if not points:
            return
        point = points[0]
        custom = point.get("customdata") if isinstance(point, dict) else getattr(point, "customdata", None)
        nav = zone_df["Ticker"].tolist()
        if custom is not None and len(custom) > 0:
            _set_holding_selection(str(custom[0]), nav_tickers=nav)
            return
        label = point.get("y") if isinstance(point, dict) else getattr(point, "y", None)
        if label:
            for _, row in zone_df.iterrows():
                if row["Ticker"] in str(label):
                    _set_holding_selection(row["Ticker"], nav_tickers=nav)
                    break

    @classmethod
    def _render_holding_focus(
        cls,
        rows: List[PortfolioDetailRow],
        preload: PortfolioAnalysisPreload,
    ) -> None:
        """Full-page dividend analysis for one holding or S&P research pick."""
        research_mode = bool(st.session_state.get("portfolio_research_mode"))
        nav_tickers: List[str] = st.session_state.get("portfolio_nav_tickers") or [
            row.ticker for row in rows
        ]
        if not nav_tickers:
            st.session_state["portfolio_view_mode"] = PORTFOLIO_VIEW_OVERVIEW
            st.session_state.pop("portfolio_research_mode", None)
            st.rerun()

        selected_symbol = (st.session_state.get("portfolio_selected_symbol") or "").upper()
        if selected_symbol not in nav_tickers:
            selected_symbol = nav_tickers[0].upper()
            st.session_state["portfolio_selected_symbol"] = selected_symbol

        nav_bar = st.columns([1, 5, 2])
        with nav_bar[0]:
            if st.button("← Back to portfolio", type="primary", use_container_width=True):
                st.session_state["portfolio_view_mode"] = PORTFOLIO_VIEW_OVERVIEW
                st.session_state.pop("portfolio_research_mode", None)
                st.rerun()
        with nav_bar[1]:
            if research_mode:
                st.subheader(f"S&P research · {selected_symbol}")
                st.caption(
                    "Decision analysis from the shared market library — "
                    "add the ticker under **Manage portfolio** to track a position."
                )
            else:
                st.subheader(cls._label_for_symbol(rows, selected_symbol))
                charts_ready = len(preload.yield_channels)
                st.caption(
                    f"Full holding analysis · {charts_ready} of {len(preload.stock_data)} "
                    "holdings with preloaded charts"
                )
        with nav_bar[2]:
            nav_label = "Switch S&P ticker" if research_mode else "Switch holding"
            selected_symbol = st.selectbox(
                nav_label,
                options=nav_tickers,
                index=nav_tickers.index(selected_symbol),
                format_func=(
                    (lambda symbol: symbol)
                    if research_mode
                    else (lambda symbol: cls._label_for_symbol(rows, symbol))
                ),
                key="portfolio_holding_nav_symbol",
            )
            st.session_state["portfolio_selected_symbol"] = selected_symbol.upper()

        if research_mode:
            cls._render_sp500_research_analysis(selected_symbol, preload)
            return

        if not st.session_state.get("portfolio_analysis_ready"):
            st.info("Use **Reload live data** in the sidebar to preload dividend charts for every holding.")
            return

        SingleStockView.render_analysis_for_symbol(
            selected_symbol,
            show_sector=False,
            data=preload.stock_data.get(selected_symbol),  # live price applied in view
            yield_channel_data=preload.yield_channels.get(selected_symbol),
            vector_doc=preload.vector_docs.get(selected_symbol),
        )

        focus_row = next((row for row in rows if row.ticker == selected_symbol), None)
        if focus_row is None and rows:
            focus_row = rows[0]
        if focus_row is not None:
            cls._render_portfolio_holding_comparison(
                selected_symbol,
                focus_row,
                rows,
                preload,
                nav_tickers,
            )

    @classmethod
    def _render_sp500_research_analysis(
        cls,
        symbol: str,
        preload: PortfolioAnalysisPreload,
    ) -> None:
        """Load and display analysis for a symbol chosen from the S&P list (not necessarily held)."""
        from services.portfolio_details_service import get_stock_data
        from services.shared_market_db import get_document
        from services.sp500_peers_service import find_sector_peers
        from services.yield_channel_chart import YieldChannelService
        from data_ingestion.portfolio_store import PortfolioStore

        symbol = symbol.upper()
        with st.spinner(f"Loading analysis for {symbol}…"):
            from services.live_price import apply_live_price

            cached = preload.stock_data.get(symbol)
            if cached is not None:
                data = apply_live_price(cached)
            else:
                data = get_stock_data(symbol)
            vector_doc = preload.vector_docs.get(symbol) or get_document(symbol)
            yield_channel = preload.yield_channels.get(symbol)
            if yield_channel is None:
                try:
                    from services.yield_channel_chart import _default_yield_channel_service

                    yield_channel = _default_yield_channel_service().fetch_yield_channel_data(
                        symbol
                    )
                except Exception:
                    yield_channel = None

        if not data:
            st.error(
                f"Could not load data for {symbol}. "
                "Run S&P ingest on the server or check the ticker."
            )
            return

        SingleStockView.render_analysis_for_symbol(
            symbol,
            show_sector=True,
            data=data,
            yield_channel_data=yield_channel,
            vector_doc=vector_doc,
        )

        portfolio_symbols = {
            holding.symbol.upper()
            for holding in PortfolioStore(seed=False).list_holdings()
        }
        if symbol in portfolio_symbols:
            st.info(f"{symbol} is already in your portfolio — use **Holdings** for position context.")

        peers = find_sector_peers(
            sector=data.sector or "",
            exclude_symbols=[symbol],
            portfolio_symbols=portfolio_symbols,
            max_peers=3,
        )
        if peers:
            st.divider()
            st.markdown("##### Compare with other S&P names (same sector)")
            st.caption("From the shared library — not limited to your holdings.")
            current_entry = cls._peer_dict_from_stock(data)
            ranked = [current_entry] + peers
            table_rows = [
                UIComponents._build_comparison_row(
                    peer,
                    is_current=peer["symbol"].upper() == symbol.upper(),
                )
                for peer in ranked
            ]
            UIComponents._display_comparison_table(table_rows)

        with st.expander("Pick another S&P ticker", expanded=False):
            from ui.sp500_research_picker import render_sp500_research_picker

            render_sp500_research_picker(key_prefix="research_inline")

    @staticmethod
    def _peer_dict_from_stock(data: StockData) -> Dict[str, Any]:
        peer_score = ScoringService.calculate_score(data)
        div_streak = (
            data.dividend_history.consecutive_years if data.dividend_history else None
        )
        div_cagr = data.dividend_history.cagr_5y if data.dividend_history else None
        return {
            "symbol": data.symbol,
            "name": data.name,
            "score": peer_score,
            "dividend_yield_pct": data.dividend_yield_pct,
            "trailing_pe": data.trailing_pe,
            "payout_ratio_pct": data.payout_ratio_pct,
            "roe_pct": data.roe_pct,
            "debt_to_equity": data.debt_to_equity,
            "div_streak": div_streak,
            "div_cagr": div_cagr,
            "dividend_tier": data.dividend_tier,
        }

    @classmethod
    def _render_portfolio_holding_comparison(
        cls,
        symbol: str,
        row: PortfolioDetailRow,
        rows: List[PortfolioDetailRow],
        preload: PortfolioAnalysisPreload,
        nav_tickers: List[str],
    ) -> None:
        """Compare the active holding with other positions in the same sector."""
        sector = row.sector
        if not sector or sector.strip().lower() in {"unknown", "n/a", ""}:
            return

        current_data = preload.stock_data.get(symbol)
        peers: List[Dict[str, Any]] = []
        for other in rows:
            if other.ticker.upper() == symbol.upper():
                continue
            if not other.sector or not sectors_match(sector, other.sector):
                continue
            data = preload.stock_data.get(other.ticker)
            if data:
                peers.append(cls._peer_dict_from_stock(data))

        st.divider()
        st.markdown("##### Compare with other holdings (same sector)")
        if not peers:
            st.info(
                "No other portfolio positions share this sector. "
                "Add another name in the same industry to compare side by side."
            )
            return

        peers.sort(key=lambda item: item["score"], reverse=True)
        ranked: List[Dict[str, Any]] = []
        if current_data:
            ranked.append(cls._peer_dict_from_stock(current_data))
        ranked.extend(peers)

        table_rows = [
            UIComponents._build_comparison_row(
                peer,
                is_current=peer["symbol"].upper() == symbol.upper(),
            )
            for peer in ranked
        ]
        UIComponents._display_comparison_table(table_rows)

        peer_cols = st.columns(min(len(peers), 4))
        for index, peer in enumerate(peers[:4]):
            peer_symbol = peer["symbol"]
            with peer_cols[index % len(peer_cols)]:
                if st.button(
                    f"Open {peer_symbol}",
                    key=f"portfolio_peer_{symbol}_{peer_symbol}",
                    use_container_width=True,
                ):
                    _set_holding_selection(peer_symbol, nav_tickers=nav_tickers)

    @classmethod
    def _render_dividend_timing_table(
        cls,
        rows: List[PortfolioDetailRow],
        timing_df: pd.DataFrame,
        *,
        table_key: str,
    ) -> None:
        if timing_df.empty:
            return
        selection = render_dividend_timing_dataframe(
            timing_df,
            table_key=table_key,
        )
        selected_rows = getattr(getattr(selection, "selection", None), "rows", None)
        if selected_rows:
            ticker = timing_df.iloc[selected_rows[0]]["Ticker"]
            nav = [row.ticker for row in rows]
            _set_holding_selection(ticker, nav_tickers=nav)

    @classmethod
    def _render_attention_table(
        cls,
        rows: List[PortfolioDetailRow],
        watch_df: pd.DataFrame,
        *,
        table_key: str,
    ) -> None:
        if watch_df.empty:
            return
        selection = st.dataframe(
            watch_df,
            width="stretch",
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key=table_key,
            column_config={
                "Weight %": st.column_config.NumberColumn(format="%.2f%%"),
                "Profit %": st.column_config.NumberColumn(format="%+.2f%%"),
            },
        )
        selected_rows = getattr(getattr(selection, "selection", None), "rows", None)
        if selected_rows:
            ticker = watch_df.iloc[selected_rows[0]]["Ticker"]
            nav = [row.ticker for row in rows]
            _set_holding_selection(ticker, nav_tickers=nav)

    @classmethod
    def _render_attention_watchlist(
        cls,
        rows: List[PortfolioDetailRow],
        preload: PortfolioAnalysisPreload,
    ) -> None:
        """Dividend timing list + risk watchlist (negative signals only)."""
        service = PortfolioAttentionService()
        include_news = st.checkbox(
            "Scan recent news for risk-flagged tickers (slower)",
            value=False,
            key="portfolio_attention_include_news",
            help="Fetches headlines for up to 15 tickers on the risk watchlist.",
        )

        summary = get_cached_attention_summary()
        if include_news:
            with st.spinner("Fetching news for risk-flagged tickers…"):
                summary = refresh_portfolio_risks(
                    force=True,
                    include_news=True,
                    rows=rows,
                    preload=preload,
                )
        elif summary is None:
            summary = service.build_summary(rows, preload)
            from services.portfolio_risk_monitor_service import PortfolioRiskMonitorService

            st.session_state[SESSION_SUMMARY_KEY] = (
                PortfolioRiskMonitorService.summary_to_store(summary)
            )
        else:
            summary = summary or service.build_summary(rows, preload)

        summary = normalize_attention_summary(summary)
        if summary is None:
            st.warning("Attention data is not available yet. Refresh the risk scan in the sidebar.")
            return

        st.markdown("##### Dividend calendar (upcoming)")
        st.caption(
            "Ex-dividend and payment dates coming up — informational only, not a risk score."
        )
        dividend_df = service.to_dataframe(summary, list_kind="dividend")
        if summary.dividend_total == 0:
            st.success("No upcoming ex-dates or payments in the next few weeks.")
        else:
            d1, d2 = st.columns(2)
            d1.metric("Upcoming events", summary.dividend_total)
            d2.metric("Ex-date within 3 weeks", summary.dividend_upcoming_ex_count)
            dividend_timing_legend()
            cls._render_dividend_timing_table(
                rows, dividend_df, table_key="portfolio_dividend_attention_table"
            )

        st.divider()
        st.markdown("##### Buy opportunities")
        st.caption(
            "Holdings in green / deep-value yield zones with supportive signals — "
            "high priority means a strong fit to research for a buy."
        )
        opp_df = service.to_dataframe(summary, list_kind="opportunity")
        if summary.opportunity_total == 0:
            st.info("No buy-zone opportunities flagged with the current rules.")
        else:
            o1, o2 = st.columns(2)
            o1.metric("Opportunities", summary.opportunity_total)
            o2.metric("High priority", summary.high_count)
            cls._render_attention_table(
                rows, opp_df, table_key="portfolio_opportunity_table"
            )

        st.divider()
        st.markdown("##### High-risk watchlist")
        st.caption(
            "Only material, compounded issues — deep losses, sell ratings, "
            "expensive yield zones while underwater, and optional bearish news."
        )
        risk_df = service.to_dataframe(summary, list_kind="risk")

        if summary.total == 0:
            st.success("No high-risk holdings right now.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("High risk", summary.total)
            by_cat = summary.by_category
            c2.metric("Exposure", by_cat.get("Exposure", 0))
            c3.metric("Estimates", by_cat.get("Estimates", 0))
            c4.metric("News", by_cat.get("News", 0))
            cls._render_attention_table(
                rows, risk_df, table_key="portfolio_attention_table"
            )

        with st.expander("What triggers each list?"):
            st.markdown(
                """
                **Dividend calendar** — upcoming ex-dates and payment dates (row colors,
                not severity). Paid events are omitted from this list.

                **Buy opportunities** — deep value / value yield zones, price below
                fair-yield level, buy-rated analysts, dividend safety, and growth streak.

                **High-risk watchlist** — only high-severity compounded problems
                (not single minor signals). News scan applies to names already at risk.
                """
            )

    @classmethod
    def _render_allocations(
        cls,
        rows: List[PortfolioDetailRow],
        *,
        key_prefix: str = "portfolio",
    ) -> None:
        """Sector and market-cap bucket charts (requires loaded holdings)."""
        allocation = PortfolioAllocationService()
        sector_df = allocation.sector_allocation(rows)
        cap_df = allocation.market_cap_allocation(rows)

        if sector_df.empty and cap_df.empty:
            st.warning("No position values available for allocation.")
            return

        st.markdown("##### Sector & market cap")
        st.caption(
            "Weights by **current position value** (USD). "
            "Market cap: **$1B–$10B**, **$10B–$200B**, **> $200B** (source: analysed stocks / Yahoo)."
        )

        chart_left, chart_right = st.columns(2)
        with chart_left:
            sector_pie = allocation.create_sector_pie(rows)
            if sector_pie:
                show_chart(
                    sector_pie,
                    width="stretch",
                    key=f"{key_prefix}_sector_pie",
                )
        with chart_right:
            cap_pie = allocation.create_market_cap_pie(rows)
            if cap_pie:
                show_chart(
                    cap_pie,
                    width="stretch",
                    key=f"{key_prefix}_mcap_pie",
                )

        sector_bar = allocation.create_sector_bar(rows)
        if sector_bar:
            show_chart(
                sector_bar,
                width="stretch",
                key=f"{key_prefix}_sector_bar",
            )

        table_left, table_right = st.columns(2)
        with table_left:
            st.markdown("**Sectors**")
            st.dataframe(
                sector_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "Value USD": st.column_config.NumberColumn(format="$%.2f"),
                    "Weight %": st.column_config.NumberColumn(format="%.2f%%"),
                },
            )
        with table_right:
            st.markdown("**Market cap**")
            display_cap = cap_df.drop(columns=["Bucket"], errors="ignore")
            st.dataframe(
                display_cap,
                width="stretch",
                hide_index=True,
                column_config={
                    "Value USD": st.column_config.NumberColumn(format="$%.2f"),
                    "Weight %": st.column_config.NumberColumn(format="%.2f%%"),
                },
            )

        with st.expander("Holdings by market-cap bucket"):
            detail = allocation.holdings_by_bucket(rows)
            st.dataframe(
                detail,
                width="stretch",
                hide_index=True,
                column_config={
                    "Market cap (B)": st.column_config.NumberColumn(format="%.2f"),
                    "Value USD": st.column_config.NumberColumn(format="$%.2f"),
                    "Weight %": st.column_config.NumberColumn(format="%.2f%%"),
                },
            )

    @classmethod
    def _render_dashboard_page(
        cls,
        rows: Optional[List[PortfolioDetailRow]] = None,
        preload: Optional[PortfolioAnalysisPreload] = None,
        *,
        compact: bool = False,
    ) -> None:
        """High-level portfolio dashboard with monthly evolution since inception."""
        _ensure_yield_preload_if_needed()
        if preload is None or st.session_state.get("portfolio_fast_loaded"):
            preload = _preload_from_session()
        service = PortfolioDashboardService()
        deposits = service.list_deposits()
        holdings_snapshot = (
            PortfolioDashboardService.holdings_from_rows(rows) if rows else None
        )
        metrics = service.build_metrics(deposits, holdings=holdings_snapshot)
        summary = metrics.deposits
        evolution = service.evolution_dataframe(deposits)

        st.markdown("##### Capital & performance (€)")
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        with c1:
            st.metric("Total deposits", f"€{summary.total_deposits_eur:,.0f}")
        with c2:
            st.metric(
                "Portfolio",
                f"€{summary.latest_portfolio_eur:,.0f}",
                help=summary.latest_label,
            )
        with c3:
            st.metric(
                "Gain vs deposits",
                f"€{summary.gain_eur:+,.0f}",
                f"{summary.gain_pct:+.1f}%" if summary.gain_pct is not None else None,
            )
        with c4:
            st.metric(
                "Portfolio CAGR",
                f"{metrics.cagr_pct:.1f}%" if metrics.cagr_pct is not None else "—",
                help="Compound annual growth on recorded portfolio value",
            )
        with c5:
            st.metric("Avg deposit/month", f"€{metrics.avg_monthly_deposit_eur:,.0f}")
        with c6:
            st.metric(
                "Last month MoM",
                f"{metrics.latest_mom_change_pct:+.1f}%"
                if metrics.latest_mom_change_pct is not None
                else "—",
            )

        if not compact:
            if holdings_snapshot:
                st.markdown("##### Current positions (USD)")
                h1, h2, h3, h4 = st.columns(4)
                with h1:
                    st.metric("Value", f"${holdings_snapshot.current_value_usd:,.0f}")
                with h2:
                    st.metric(
                        "Profit",
                        f"${holdings_snapshot.profit_usd:+,.0f}",
                        f"{holdings_snapshot.profit_pct:+.1f}%"
                        if holdings_snapshot.profit_pct is not None
                        else None,
                    )
                with h3:
                    st.metric(
                        "Annual income",
                        f"${holdings_snapshot.annual_dividend_income_usd:,.0f}",
                    )
                with h4:
                    st.metric(
                        "Dividends received",
                        f"${holdings_snapshot.lifetime_dividends_usd:,.0f}",
                    )
            elif rows:
                st.caption("Run **Refresh lists** in the sidebar for watchlists below.")

        if rows and preload and st.session_state.get("portfolio_analysis_ready"):
            st.divider()
            cls._render_attention_watchlist(rows, preload)

        st.markdown("##### Portfolio evolution (€)")
        evolution_chart = service.create_evolution_chart(deposits)
        if evolution_chart:
            show_chart(
                evolution_chart,
                width="stretch",
                key="portfolio_dashboard_evolution",
            )

        left, right = st.columns(2)
        with left:
            flow_chart = service.create_monthly_flow_chart(deposits)
            if flow_chart:
                show_chart(
                    flow_chart,
                    width="stretch",
                    key="portfolio_dashboard_flow",
                )
        with right:
            gain_chart = service.create_gain_chart(deposits)
            if gain_chart:
                show_chart(
                    gain_chart,
                    width="stretch",
                    key="portfolio_dashboard_gain",
                )

        if metrics.best_month_gain_pct is not None:
            st.caption(
                f"Best month (MoM): **{metrics.best_month_label}** "
                f"({metrics.best_month_gain_pct:+.1f}%) • "
                f"Tracking {summary.month_count} months "
                f"({metrics.months_since_start} calendar months)"
            )

        st.markdown("#### Monthly evolution")
        display = evolution.copy()
        if not display.empty:
            display = display.rename(
                columns={
                    "label": "Month",
                    "deposit_eur": "Deposit €",
                    "portfolio_eur": "Portfolio €",
                    "cumulative_deposits_eur": "Cumulative deposits €",
                    "gain_vs_deposits_eur": "Gain vs deposits €",
                    "mom_change_pct": "MoM change %",
                }
            )
            show_cols = [
                "Month",
                "Deposit €",
                "Portfolio €",
                "Cumulative deposits €",
                "Gain vs deposits €",
                "MoM change %",
            ]
            st.dataframe(
                display[show_cols],
                width="stretch",
                hide_index=True,
                column_config={
                    "Deposit €": st.column_config.NumberColumn(format="€%.2f"),
                    "Portfolio €": st.column_config.NumberColumn(format="€%.2f"),
                    "Cumulative deposits €": st.column_config.NumberColumn(format="€%.2f"),
                    "Gain vs deposits €": st.column_config.NumberColumn(format="€%+.2f"),
                    "MoM change %": st.column_config.NumberColumn(format="%+.2f%%"),
                },
            )

    @classmethod
    def _render_benchmark_comparison(cls, deposits: List[MonthlyDeposit]) -> None:
        """Compare actual portfolio to index/ETF DCA using recorded monthly share buys."""
        st.markdown("##### Benchmark comparison (S&P 500 & SCHD)")
        st.caption(
            "Same monthly share purchases as on the deposits sheet. "
            "Month-end closing prices (Yahoo Finance), converted to €."
        )

        try:
            comparison_df = _load_benchmark_comparison()
        except Exception as exc:
            st.warning(f"Could not load benchmark prices: {exc}")
            return

        if comparison_df.empty:
            st.info("No benchmark comparison data available.")
            return

        benchmark_svc = PortfolioBenchmarkService()
        yearly_df = benchmark_svc.build_yearly_summary(comparison_df)

        eur_cols = ["Portfolio €", "S&P 500 €", "SCHD €"]
        if not any(
            col in comparison_df.columns and comparison_df[col].notna().any()
            for col in eur_cols
        ):
            st.warning(
                "Benchmark values could not be priced (check internet / Yahoo Finance). "
                "Yearly tables still show deposits; reload when online for full charts."
            )

        latest = benchmark_svc.latest_comparison(comparison_df, deposits)
        portfolio_val = latest.get("Portfolio", 0.0)
        sp500_val = latest.get("S&P 500", 0.0)
        schd_val = latest.get("SCHD", 0.0)

        m1, m2, m3 = st.columns(3)
        m1.metric("Portfolio (actual)", f"€{portfolio_val:,.0f}")
        m2.metric(
            "S&P 500 (DCA)",
            f"€{sp500_val:,.0f}",
            f"{sp500_val - portfolio_val:+,.0f} vs portfolio" if sp500_val else None,
            delta_color="inverse" if sp500_val > portfolio_val else "normal",
        )
        m3.metric(
            "SCHD (DCA)",
            f"€{schd_val:,.0f}",
            f"{schd_val - portfolio_val:+,.0f} vs portfolio" if schd_val else None,
            delta_color="inverse" if schd_val > portfolio_val else "normal",
        )

        focused = benchmark_svc.create_focused_comparison_chart(comparison_df)
        if focused:
            show_chart(
                focused,
                width="stretch",
                key="portfolio_sp500_schd_timeline",
            )

        if not yearly_df.empty:
            st.markdown("##### Annual distribution & performance")
            y_left, y_right = st.columns(2)
            with y_left:
                end_chart = benchmark_svc.create_yearly_end_values_chart(yearly_df)
                if end_chart:
                    show_chart(
                        end_chart,
                        width="stretch",
                        key="portfolio_yearly_eoy",
                    )
            with y_right:
                dist_chart = benchmark_svc.create_yearly_distribution_chart(yearly_df)
                if dist_chart:
                    show_chart(
                        dist_chart,
                        width="stretch",
                        key="portfolio_yearly_distribution",
                    )

            ret_chart = benchmark_svc.create_yearly_returns_chart(yearly_df)
            if ret_chart:
                show_chart(
                    ret_chart,
                    width="stretch",
                    key="portfolio_yearly_returns",
                )

            dep_chart = benchmark_svc.create_yearly_deposits_chart(yearly_df)
            if dep_chart:
                show_chart(
                    dep_chart,
                    width="stretch",
                    key="portfolio_yearly_deposits",
                )

            st.dataframe(
                yearly_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "Deposits €": st.column_config.NumberColumn(format="€%.2f"),
                    "Portfolio (EOY) €": st.column_config.NumberColumn(format="€%.2f"),
                    "S&P 500 (EOY) €": st.column_config.NumberColumn(format="€%.2f"),
                    "SCHD (EOY) €": st.column_config.NumberColumn(format="€%.2f"),
                    "Portfolio YoY %": st.column_config.NumberColumn(format="%+.2f%%"),
                    "S&P 500 YoY %": st.column_config.NumberColumn(format="%+.2f%%"),
                    "SCHD YoY %": st.column_config.NumberColumn(format="%+.2f%%"),
                },
            )

        st.markdown("##### All benchmarks (monthly)")
        with st.expander("Dow Jones, Nasdaq & full monthly detail"):
            compare_chart = benchmark_svc.create_comparison_chart(deposits)
            if compare_chart:
                show_chart(
                    compare_chart,
                    width="stretch",
                    key="portfolio_benchmark_comparison",
                )
            display_cols = [
                "Month",
                "Deposit €",
                "Portfolio €",
                "S&P 500 €",
                "SCHD €",
                "Dow Jones €",
                "Nasdaq €",
            ]
            show = [column for column in display_cols if column in comparison_df.columns]
            st.dataframe(
                comparison_df[show],
                width="stretch",
                hide_index=True,
            )
            st.caption("Full detail (including cumulative shares and USD)")
            st.dataframe(comparison_df, width="stretch", hide_index=True)

        st.download_button(
            "Download monthly comparison CSV",
            comparison_df.to_csv(index=False),
            "portfolio_benchmark_comparison.csv",
            "text/csv",
            key="portfolio_benchmark_csv",
        )
        if not yearly_df.empty:
            st.download_button(
                "Download yearly summary CSV",
                yearly_df.to_csv(index=False),
                "portfolio_benchmark_yearly.csv",
                "text/csv",
                key="portfolio_benchmark_yearly_csv",
            )

    @classmethod
    def _render_purchase_journal_page(cls) -> None:
        """Chronological log of stock purchases (current portfolio only)."""
        service = PortfolioPurchaseJournalService()
        records = service.list_purchases()
        summary = service.summarize(records)

        st.markdown("##### Summary")
        st.caption("Excludes removed tickers: AMCR, CCI, INTC, LEG, OHI, VFC, WBA.")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Recorded transactions", summary.total_lots)
        with c2:
            st.metric("Tickers with purchases", summary.symbols_with_buys)
        with c3:
            st.metric("First purchase", summary.first_purchase)
        with c4:
            st.metric("Last purchase", summary.last_purchase)

        missing = service.symbols_without_journal()
        if missing:
            st.info(
                "No journal data (but in portfolio): "
                + ", ".join(missing)
            )

        st.markdown("##### Purchase tables")
        by_symbol = service.by_symbol_dataframe(records)
        st.dataframe(
            by_symbol,
            width="stretch",
            hide_index=True,
            column_config={
                "Shares": st.column_config.NumberColumn(format="%.0f"),
                "Avg price $": st.column_config.NumberColumn(format="$%.2f"),
                "DB avg cost $": st.column_config.NumberColumn(format="$%.2f"),
            },
        )
        chrono = service.chronological_dataframe(records)
        st.dataframe(
            chrono,
            width="stretch",
            hide_index=True,
            column_config={"Price $": st.column_config.NumberColumn(format="$%.2f")},
        )
        st.download_button(
            "Download purchase journal CSV",
            chrono.to_csv(index=False),
            "purchase_journal.csv",
            "text/csv",
            key="purchase_journal_csv",
        )

        st.markdown("##### Acquisition split (estimated)")
        st.caption(
            "Shares per buy are split evenly across journal lines; "
            "values scale to portfolio acquisition cost."
        )
        split_df = service.acquisition_split_dataframe(records)
        if not split_df.empty:
            total_val = split_df["Journal value $"].sum()
            total_lots = split_df["# Purchases"].sum()
            s1, s2, s3 = st.columns(3)
            s1.metric("Total value (journal)", f"${total_val:,.0f}")
            s2.metric("Total transactions", int(total_lots))
            s3.metric("Tickers", len(split_df))

            t_left, t_right = st.columns(2)
            with t_left:
                treemap = service.create_acquisition_value_treemap(records)
                if treemap:
                    show_chart(
                        treemap,
                        width="stretch",
                        key="purchase_journal_treemap",
                    )
            with t_right:
                lots_pie = service.create_lots_count_pie(records)
                if lots_pie:
                    show_chart(
                        lots_pie,
                        width="stretch",
                        key="purchase_journal_lots_pie",
                    )

            dual = service.create_dual_split_bar(records)
            if dual:
                show_chart(dual, width="stretch", key="purchase_journal_dual_bar")

            bubble = service.create_value_vs_lots_chart(records)
            if bubble:
                show_chart(bubble, width="stretch", key="purchase_journal_bubble")

            st.dataframe(
                split_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "Shares": st.column_config.NumberColumn(format="%.0f"),
                    "Journal value $": st.column_config.NumberColumn(format="$%.2f"),
                    "DB value $": st.column_config.NumberColumn(format="$%.2f"),
                    "% of value": st.column_config.NumberColumn(format="%.2f%%"),
                    "% of trades": st.column_config.NumberColumn(format="%.2f%%"),
                },
            )

            with st.expander("Per-transaction detail (estimated shares & value)"):
                st.dataframe(
                    service.lot_estimates_dataframe(records),
                    width="stretch",
                    hide_index=True,
                )

        with st.expander("Timeline & price charts", expanded=False):
            timeline = service.create_timeline_chart(records)
            if timeline:
                show_chart(timeline, width="stretch", key="purchase_journal_timeline")
            left, right = st.columns(2)
            with left:
                yearly = service.create_yearly_activity_chart(records)
                if yearly:
                    show_chart(yearly, width="stretch", key="purchase_journal_yearly")
            with right:
                price_chart = service.create_price_scatter_by_symbol(records)
                if price_chart:
                    show_chart(price_chart, width="stretch", key="purchase_journal_prices")

    @classmethod
    def _render_dividend_growth_page(cls) -> None:
        """Annual dividend per share and growth since 2021 for all holdings."""
        try:
            growth_data = _load_dividend_growth()
        except Exception as exc:
            st.warning(f"Could not load dividend history: {exc}")
            return

        service = PortfolioDividendGrowthService()

        st.markdown(f"##### Overview (since {SINCE_YEAR})")
        st.caption(
            "Annual dividend per share from analysed stocks. "
            "Green heatmap cells = higher DPS vs prior years."
        )

        if not growth_data:
            st.info(
                "No dividend history in the database for current positions. "
                "Run `python ingest_data.py --enrich-existing`."
            )
            return

        with_growth = sum(1 for item in growth_data if item.growth_years > 0)
        avg_cagr = [
            item.cagr_since_start
            for item in growth_data
            if item.cagr_since_start is not None
        ]
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Symbols with history", len(growth_data))
        with m2:
            st.metric("With recent growth", with_growth)
        with m3:
            st.metric(
                "Avg CAGR %",
                f"{sum(avg_cagr) / len(avg_cagr):.1f}%" if avg_cagr else "—",
            )
        with m4:
            cash_latest = service.portfolio_cash_by_year(growth_data)
            latest_cash = (
                float(cash_latest.iloc[-1]["Est. dividends $"])
                if not cash_latest.empty
                else 0
            )
            st.metric(f"Cash {cash_latest.iloc[-1]['Year'] if not cash_latest.empty else '—'}", f"${latest_cash:,.0f}")

        portfolio_cash = service.create_portfolio_cash_chart(growth_data)
        if portfolio_cash:
            show_chart(
                portfolio_cash,
                width="stretch",
                key="dividend_growth_portfolio_cash",
            )

        heatmap = service.create_annual_heatmap(growth_data)
        if heatmap:
            show_chart(
                heatmap,
                width="stretch",
                key="dividend_growth_heatmap",
            )

        yoy_heat = service.create_yoy_heatmap(growth_data)
        if yoy_heat:
            show_chart(
                yoy_heat,
                width="stretch",
                key="dividend_growth_yoy",
            )

        tickers = sorted(item.symbol for item in growth_data)
        selected = st.multiselect(
            "Select tickers for line chart",
            tickers,
            default=tickers[:12],
            key="dividend_growth_ticker_filter",
        )
        filtered = [item for item in growth_data if item.symbol in selected]
        if filtered:
            lines = service.create_growth_lines_chart(filtered, max_lines=len(filtered))
            if lines:
                show_chart(
                    lines,
                    width="stretch",
                    key="dividend_growth_lines",
                )

        st.markdown("##### Annual dividend / share (table)")
        matrix = service.annual_matrix_dataframe(growth_data)
        year_cols = [column for column in matrix.columns if column.isdigit()]
        st.dataframe(
            matrix,
            width="stretch",
            hide_index=True,
            column_config={
                **{year: st.column_config.NumberColumn(format="$%.4f") for year in year_cols},
                "CAGR %": st.column_config.NumberColumn(format="%+.2f%%"),
            },
        )

        with st.expander("YoY growth (%) — by ticker"):
            st.dataframe(
                service.yoy_growth_matrix(growth_data),
                width="stretch",
                hide_index=True,
            )

        st.download_button(
            "Download dividend growth CSV",
            matrix.to_csv(index=False),
            "portfolio_dividend_growth.csv",
            "text/csv",
            key="dividend_growth_csv",
        )

    @classmethod
    def _render_dividends_tab(
        cls,
        rows: Optional[List[PortfolioDetailRow]] = None,
        preload: Optional[PortfolioAnalysisPreload] = None,
    ) -> None:
        """Monthly dividend calendar plus net cash received (after tax)."""

        if (
            rows
            and preload
            and st.session_state.get("portfolio_analysis_ready")
        ):
            st.markdown("##### 1. Monthly dividend calendar")
            st.caption(
                "Highlights **upcoming** ex-dates and payments vs **paid** cash — "
                "notifications only, not risk severity."
            )
            cls._render_monthly_dividend_exposure(rows, preload)
        else:
            st.info(
                "Load portfolio details in the sidebar to show the monthly dividend calendar."
            )

        st.divider()
        st.markdown("##### 2. Net dividends received")
        cls._render_dividend_income_page()

    @classmethod
    def _render_dividend_income_page(cls) -> None:
        """Net dividend cash received (after withholding tax)."""
        service = PortfolioDividendIncomeService()
        records = service.list_dividends()
        summary = service.summarize(records)
        pivot = service.pivot_net_dataframe(records)
        yearly = service.yearly_summary(records)
        detail = service.detail_dataframe(records)

        st.caption(
            "Cash received **after tax**, auto-calculated from your holdings' dividend history. "
            "**10%** withholding through end of 2025, **16%** from 2026."
        )

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        with c1:
            st.metric("Total net", f"${summary.total_net_usd:,.2f}")
        with c2:
            st.metric("Total gross (est.)", f"${summary.total_gross_usd:,.2f}")
        with c3:
            st.metric("Total tax (est.)", f"${summary.total_tax_usd:,.2f}")
        with c4:
            st.metric(f"YTD {summary.ytd_year} net", f"${summary.ytd_net_usd:,.2f}")
        with c5:
            st.metric(
                "Best year",
                f"${summary.best_year_net:,.0f}",
                str(summary.best_year),
            )
        with c6:
            st.metric("Avg / month", f"${summary.avg_monthly_net:,.2f}")

        chart_left, chart_right = st.columns(2)
        with chart_left:
            yearly_chart = service.create_yearly_bar_chart(records)
            if yearly_chart:
                show_chart(
                    yearly_chart,
                    width="stretch",
                    key="dividend_income_yearly",
                )
        with chart_right:
            cumulative = service.create_cumulative_chart(records)
            if cumulative:
                show_chart(
                    cumulative,
                    width="stretch",
                    key="dividend_income_cumulative",
                )

        monthly_chart = service.create_monthly_by_year_chart(records)
        if monthly_chart:
            show_chart(
                monthly_chart,
                width="stretch",
                key="dividend_income_monthly_years",
            )

        heatmap = service.create_heatmap_chart(records)
        if heatmap:
            show_chart(
                heatmap,
                width="stretch",
                key="motion_dividend_heatmap",
            )

        st.markdown("#### Net dividends — annual pivot")
        year_cols = [column for column in pivot.columns if column != "Month"]
        st.dataframe(
            pivot,
            width="stretch",
            hide_index=True,
            column_config={
                col: st.column_config.NumberColumn(format="$%.2f")
                for col in year_cols
            },
        )

        st.markdown("#### Yearly summary")
        st.dataframe(
            yearly,
            width="stretch",
            hide_index=True,
            column_config={
                "Net $": st.column_config.NumberColumn(format="$%.2f"),
                "Gross $": st.column_config.NumberColumn(format="$%.2f"),
                "Tax withheld $": st.column_config.NumberColumn(format="$%.2f"),
                "Tax %": st.column_config.NumberColumn(format="%.0f%%"),
            },
        )

        with st.expander("Monthly detail (net, gross, tax)"):
            st.dataframe(
                detail,
                width="stretch",
                hide_index=True,
                column_config={
                    "Net $": st.column_config.NumberColumn(format="$%.2f"),
                    "Gross $": st.column_config.NumberColumn(format="$%.2f"),
                    "Tax withheld $": st.column_config.NumberColumn(format="$%.2f"),
                    "Tax %": st.column_config.NumberColumn(format="%.0f%%"),
                },
            )

        st.download_button(
            "Download dividend income CSV",
            detail.to_csv(index=False),
            "dividend_income_monthly.csv",
            "text/csv",
            key="dividend_income_csv",
        )

    @classmethod
    def _render_deposits_page(cls) -> None:
        """Monthly deposits and portfolio value history."""
        service = PortfolioDepositsService()
        deposits = service.list_deposits()
        summary = service.summarize(deposits)
        df = service.to_dataframe(deposits)

        st.markdown("##### Account deposits & recorded portfolio value")
        st.caption("Monthly deposits (€ and $) and portfolio value at each month end.")

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Total deposits €", f"€{summary.total_deposits_eur:,.2f}")
        with col2:
            st.metric("Total deposits $", f"${summary.total_deposits_usd:,.2f}")
        with col3:
            st.metric(
                "Portfolio €",
                f"€{summary.latest_portfolio_eur:,.2f}",
                help=f"Latest recorded value: {summary.latest_label}",
            )
        with col4:
            st.metric(
                "Gain vs deposits",
                f"€{summary.gain_eur:+,.2f}",
                f"{summary.gain_pct:+.1f}%" if summary.gain_pct is not None else None,
            )
        with col5:
            st.metric("Months recorded", summary.month_count)

        chart = service.create_deposits_chart(deposits)
        if chart:
            show_chart(chart, width="stretch", key="portfolio_deposits_timeline")

        cum_chart = service.create_cumulative_chart(deposits)
        if cum_chart:
            show_chart(cum_chart, width="stretch", key="portfolio_deposits_cumulative")

        st.markdown("##### Monthly detail table")
        st.dataframe(
            df,
            width="stretch",
            hide_index=True,
            column_config={
                "Deposit €": st.column_config.NumberColumn(format="€%.2f"),
                "Deposit $": st.column_config.NumberColumn(format="$%.2f"),
                "Portfolio €": st.column_config.NumberColumn(format="€%.2f"),
            },
        )

        st.download_button(
            "Download deposits CSV",
            df.to_csv(index=False),
            "portfolio_deposits.csv",
            "text/csv",
            key="portfolio_deposits_csv",
        )

        st.divider()
        cls._render_benchmark_comparison(deposits)

    @classmethod
    def _render_holding_drilldown(
        cls,
        symbol: str,
        row: PortfolioDetailRow,
        rows: List[PortfolioDetailRow],
        preload: PortfolioAnalysisPreload,
        nav_tickers: List[str],
    ) -> None:
        """Inline purchase journal and dividend cash history for one holding."""
        detail_svc = PortfolioHoldingDetailService()
        document = preload.vector_docs.get(symbol)
        summary = detail_svc.summarize(
            symbol, document, current_shares=row.shares
        )

        st.caption(f"**{symbol}** — {row.company}")

        from ui.analysis_evidence import render_analysis_evidence

        render_analysis_evidence(
            symbol,
            data=preload.stock_data.get(symbol),
            vector_doc=document,
            yield_channel_data=preload.yield_channels.get(symbol),
            portfolio_prices_at=st.session_state.get("portfolio_details_time"),
            expanded=False,
        )

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Journal buys", summary.purchase_count)
        m2.metric("Est. cost (journal)", f"${summary.total_estimated_cost_usd:,.2f}")
        m3.metric("Dividend payments", summary.dividend_payment_count)
        m4.metric("Est. dividends received", f"${summary.total_dividend_cash_usd:,.2f}")

        if summary.uses_journal_shares:
            st.caption(
                "Shares per buy are estimated from the purchase journal (even split, "
                "scaled to portfolio acquisition value). Dividend cash = $/share × "
                "shares held on each ex-date."
            )
        else:
            st.caption(
                "No purchase journal for this ticker — dividend cash uses current "
                f"share count ({row.shares:.0f}) for all historical payments."
            )

        buy_col, div_col = st.columns(2)
        purchases_df = detail_svc.purchases_dataframe(symbol)
        dividends_df = detail_svc.dividends_dataframe(
            symbol, document, current_shares=row.shares
        )

        with buy_col:
            st.markdown("**All purchases (journal)**")
            if purchases_df.empty:
                st.info("No purchase journal entries for this ticker.")
            else:
                st.dataframe(
                    purchases_df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Price $": st.column_config.NumberColumn(format="$%.2f"),
                        "Est. shares": st.column_config.NumberColumn(format="%.4f"),
                        "Est. cost $": st.column_config.NumberColumn(format="$%.2f"),
                        "Cumulative shares": st.column_config.NumberColumn(format="%.4f"),
                    },
                )

        with div_col:
            st.markdown("**Dividends received (from analysed stocks history)**")
            if dividends_df.empty:
                st.info("No dividend payment history in the database for this ticker.")
            else:
                st.dataframe(
                    dividends_df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "$/share": st.column_config.NumberColumn(format="$%.4f"),
                        "Shares held": st.column_config.NumberColumn(format="%.4f"),
                        "Cash $": st.column_config.NumberColumn(format="$%.2f"),
                        "Ex-date": st.column_config.DateColumn(format="YYYY-MM-DD"),
                        "Pay date": st.column_config.DateColumn(format="YYYY-MM-DD"),
                    },
                )

        cls._render_portfolio_holding_comparison(
            symbol, row, rows, preload, nav_tickers
        )

        action_left, action_right = st.columns([1, 3])
        with action_left:
            if st.button(
                "Open full-page analysis",
                type="secondary",
                key=f"holding_drill_open_{symbol}",
                use_container_width=True,
            ):
                _set_holding_selection(symbol, nav_tickers=nav_tickers)

    @classmethod
    def _render_holdings_overview(
        cls,
        rows: List[PortfolioDetailRow],
        preload: PortfolioAnalysisPreload,
        loaded_at: datetime,
    ) -> None:
        _ensure_yield_preload_if_needed()
        preload = _preload_from_session()
        ready = st.session_state.get("portfolio_analysis_ready", False)
        chart_count = len(preload.yield_channels)
        st.caption(
            f"Loaded {loaded_at.strftime('%Y-%m-%d %H:%M')} · "
            f"{chart_count} yield channels"
            + (" · ready" if ready else "")
        )

        from ui.analysis_evidence import render_portfolio_session_evidence

        render_portfolio_session_evidence(
            loaded_at=loaded_at,
            holding_count=len(rows),
            charts_ready=chart_count,
            library_ready=len(preload.vector_docs),
            expanded=False,
        )

        df = cls._rows_to_dataframe(rows, preload)

        filtered = cls._render_filters(df)
        filtered_tickers = filtered["Ticker"].tolist()
        st.session_state["portfolio_nav_tickers"] = filtered_tickers

        st.markdown("##### Positions table")
        table_selection = st.dataframe(
            filtered,
            width="stretch",
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="portfolio_holdings_table",
            column_config={
                "Company": st.column_config.TextColumn(
                    help="Select a row to update the holding detail panel below."
                ),
                "Ticker": st.column_config.TextColumn(
                    help="Select a row to update the holding detail panel below."
                ),
                "P/E Ratio": st.column_config.NumberColumn(format="%.2f"),
                "Shares": st.column_config.NumberColumn(format="%.0f"),
                "Current Price": st.column_config.NumberColumn(format="$%.2f"),
                "Current Value": st.column_config.NumberColumn(format="$%.2f"),
                "Avg Cost/Share": st.column_config.NumberColumn(format="$%.2f"),
                "Acquisition Value": st.column_config.NumberColumn(format="$%.2f"),
                "Profit": st.column_config.NumberColumn(format="$%.2f"),
                "Profit %": st.column_config.NumberColumn(format="%.2f%%"),
                "Est. Avg Price": st.column_config.NumberColumn(format="$%.2f"),
                "Medium Price Last 365 Days": st.column_config.NumberColumn(format="$%.2f"),
                "180 Day Price": st.column_config.NumberColumn(format="$%.2f"),
                "365 Day Price": st.column_config.NumberColumn(format="$%.2f"),
                "180": st.column_config.NumberColumn(format="%+.1f%%"),
                "365 Day %": st.column_config.NumberColumn(format="%+.1f%%"),
                "Weight %": st.column_config.NumberColumn(format="%.2f%%"),
                "Div Yield %": st.column_config.NumberColumn(format="%.2f%%"),
                "Div/Share": st.column_config.NumberColumn(format="$%.3f"),
                "Income/Year": st.column_config.NumberColumn(format="$%.2f"),
                "Div Weight %": st.column_config.NumberColumn(format="%.2f%%"),
                "Income Weight %": st.column_config.NumberColumn(format="%.2f%%"),
                "Div Paid": st.column_config.NumberColumn(format="$%.2f"),
                "Growth Years": st.column_config.NumberColumn(format="%d"),
                "Commission": st.column_config.NumberColumn(format="$%.2f"),
                "% of Total Acquisitions": st.column_config.NumberColumn(format="%.2f%%"),
                "P/FCF": st.column_config.NumberColumn(format="%.2f"),
                "Ex Dividend Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
                "Dividend Pay Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
            },
        )

        selected_rows = getattr(getattr(table_selection, "selection", None), "rows", None)
        if selected_rows:
            st.session_state["portfolio_holdings_drill_ticker"] = filtered.iloc[
                selected_rows[0]
            ]["Ticker"]

        if filtered_tickers:
            if (
                st.session_state.get("portfolio_holdings_drill_ticker")
                not in filtered_tickers
            ):
                st.session_state["portfolio_holdings_drill_ticker"] = filtered_tickers[0]

            drill_ticker = st.selectbox(
                "Holding detail",
                filtered_tickers,
                format_func=lambda symbol: cls._label_for_symbol(rows, symbol),
                key="portfolio_holdings_drill_ticker",
                help="All journal purchases and estimated dividend cash for this position.",
            )
            drill_row = next(row for row in rows if row.ticker == drill_ticker)
            st.divider()
            st.markdown("##### Holding detail")
            cls._render_holding_drilldown(
                drill_ticker, drill_row, rows, preload, filtered_tickers
            )

        st.caption(f"Showing {len(filtered)} of {len(df)} positions")

        export_df = filtered.drop(columns=["Data Source"], errors="ignore")
        st.download_button(
            "Download CSV",
            export_df.to_csv(index=False),
            f"portfolio_details_{loaded_at.strftime('%Y%m%d')}.csv",
            "text/csv",
            key="portfolio_holdings_csv",
        )

        st.divider()
        cls._render_zone_overview(rows, preload, filtered_tickers)
        st.divider()
        cls._render_allocations(rows, key_prefix="holdings")

    @classmethod
    def _render_portfolio_section(cls, section: str) -> None:
        """Render one portfolio workspace section."""
        rows_loaded = st.session_state.get("portfolio_details_rows")
        portfolio_preload = (
            _preload_from_session()
            if rows_loaded and st.session_state.get("portfolio_analysis_ready")
            else None
        )

        if section == "dashboard":
            cls._render_dashboard_page(
                rows_loaded,
                preload=portfolio_preload,
                compact=True,
            )
        elif section == "holdings":
            if not rows_loaded:
                st.info("Load data with **Reload live data** in the sidebar.")
                return
            rows = st.session_state["portfolio_details_rows"]
            loaded_at = st.session_state["portfolio_details_time"]
            cls._render_holdings_overview(
                rows,
                portfolio_preload or _preload_from_session(),
                loaded_at,
            )
        elif section == "dividends":
            cls._render_dividends_tab(rows_loaded, preload=portfolio_preload)
        elif section == "dividend_growth":
            cls._render_tab_header("dividend_growth", show_refresh=True)
            cls._render_dividend_growth_page()
        elif section == "journal":
            cls._render_tab_header("journal", show_refresh=True)
            cls._render_purchase_journal_page()
        elif section == "deposits":
            cls._render_tab_header("deposits", show_refresh=True)
            cls._render_deposits_page()

    @classmethod
    def render(cls) -> None:
        from services.portfolio_session import sync_portfolio_session_with_db
        from ui.portfolio_home import render_empty_home, render_portfolio_home_header

        sync_portfolio_session_with_db()

        if st.session_state.get("portfolio_view_mode") == PORTFOLIO_VIEW_HOLDING:
            research_mode = bool(st.session_state.get("portfolio_research_mode"))
            if research_mode:
                rows = st.session_state.get("portfolio_details_rows") or []
                cls._render_holding_focus(rows, _preload_from_session())
                return
            if not portfolio_data_ready():
                st.session_state["portfolio_view_mode"] = PORTFOLIO_VIEW_OVERVIEW
                render_empty_home()
                return
            if "portfolio_details_rows" not in st.session_state:
                st.info("Use **Reload live data** in the sidebar.")
                return
            cls._render_holding_focus(
                st.session_state["portfolio_details_rows"],
                _preload_from_session(),
            )
            return

        rows_loaded = st.session_state.get("portfolio_details_rows")
        if not render_portfolio_home_header(rows_loaded):
            return

        section_key = pick_portfolio_section()
        render_portfolio_status_line()
        cls._render_portfolio_section(section_key)

