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
from ui.portfolio_risk_panel import (
    get_cached_attention_summary,
    refresh_portfolio_risks,
    store_portfolio_payload,
)
from services.portfolio_holding_detail_service import PortfolioHoldingDetailService
from ui.views import SingleStockView
from utils.formatting import format_large_number

PORTFOLIO_VIEW_OVERVIEW = "overview"
PORTFOLIO_VIEW_HOLDING = "holding"

# What each tab is for (shown as a single scope line under the tab title).
PORTFOLIO_TAB_SCOPES: dict[str, tuple[str, str]] = {
    "dashboard": (
        "Dashboard",
        "Deposits & portfolio value (€) · performance · dividend attention · risk watchlist · USD snapshot",
    ),
    "dividends": (
        "Dividends",
        "Monthly dividend calendar · net cash received (after tax)",
    ),
    "dividend_growth": (
        "Dividend growth",
        "Annual dividend per share & YoY growth from vector DB (not cash timing)",
    ),
    "journal": (
        "Purchase journal",
        "Buy dates & prices · estimated shares per lot · acquisition splits",
    ),
    "holdings": (
        "Holdings",
        "All positions · per-ticker purchases & dividends · yield zones · allocation",
    ),
    "deposits": (
        "Deposits & benchmarks",
        "Account deposits (€/$) · portfolio vs S&P 500 / SCHD DCA comparison",
    ),
}


def _set_holding_selection(symbol: str, nav_tickers: Optional[List[str]] = None) -> None:
    """Switch to full-page holding analysis for the chosen symbol."""
    st.session_state["portfolio_selected_symbol"] = symbol
    st.session_state["portfolio_view_mode"] = PORTFOLIO_VIEW_HOLDING
    st.session_state["portfolio_analysis_ready"] = True
    if nav_tickers is not None:
        st.session_state["portfolio_nav_tickers"] = nav_tickers
    st.rerun()


@st.cache_data(ttl=3600, show_spinner="Loading benchmark index prices…")
def _load_benchmark_comparison() -> pd.DataFrame:
    return PortfolioBenchmarkService().build_comparison_dataframe()


@st.cache_data(ttl=3600, show_spinner="Loading dividend history for portfolio…")
def _load_dividend_growth():
    return PortfolioDividendGrowthService().build_symbol_growth()


def _load_portfolio_payload() -> tuple[
    List[PortfolioDetailRow],
    PortfolioAnalysisPreload,
]:
    """Load holdings table + analysis preload (not Streamlit-cached; stored in session_state)."""
    return PortfolioDetailsService().build_rows_with_cache()


def _preload_from_session() -> PortfolioAnalysisPreload:
    return PortfolioAnalysisPreload(
        stock_data=st.session_state.get("portfolio_stock_cache", {}),
        yield_channels=st.session_state.get("portfolio_yield_cache", {}),
        vector_docs=st.session_state.get("portfolio_vector_docs", {}),
    )


class PortfolioDetailsView:
    """Render the full portfolio details table."""

    @staticmethod
    def _render_tab_header(tab_key: str) -> None:
        title, scope = PORTFOLIO_TAB_SCOPES[tab_key]
        st.subheader(title)
        st.caption(scope)

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
            "Last month uses **actual dividend payments** recorded in the vector database "
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
            st.plotly_chart(comparison, width="stretch", key="portfolio_monthly_comparison")

        payers_chart = create_month_payers_chart(current)
        if payers_chart:
            st.plotly_chart(payers_chart, width="stretch", key="portfolio_monthly_payers")
        elif current.payer_count == 0:
            st.info("No dividend payments expected this month based on available history.")

        st.markdown(f"#### Paying this month ({current.label})")
        if not current.holdings:
            st.caption("No holdings matched the current-month dividend schedule.")
        else:
            payer_rows = []
            for item in current.holdings:
                payer_rows.append(
                    {
                        "Ticker": item.symbol,
                        "Company": item.company,
                        "Status": item.status.title(),
                        "Ex-Date": item.ex_date,
                        "Pay Date": item.payment_date,
                        "Per Share": item.per_share,
                        "Shares": item.shares,
                        "Expected Cash": item.expected_cash,
                    }
                )
            payer_df = pd.DataFrame(payer_rows)
            payer_selection = st.dataframe(
                payer_df,
                width="stretch",
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="portfolio_monthly_payer_table",
                column_config={
                    "Per Share": st.column_config.NumberColumn(format="$%.4f"),
                    "Shares": st.column_config.NumberColumn(format="%.0f"),
                    "Expected Cash": st.column_config.NumberColumn(format="$%.2f"),
                    "Ex-Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
                    "Pay Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
                },
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
                            "Pay Date": item.payment_date,
                            "Per Share": item.per_share,
                            "Shares": item.shares,
                            "Received": item.expected_cash,
                        }
                        for item in last.holdings
                    ]
                )
                st.dataframe(detail, width="stretch", hide_index=True)

        with st.expander(f"Next month detail — {next_month.label} (expected)"):
            if not next_month.holdings:
                st.write("No expected payers.")
            else:
                detail = pd.DataFrame(
                    [
                        {
                            "Ticker": item.symbol,
                            "Company": item.company,
                            "Status": item.status.title(),
                            "Expected Cash": item.expected_cash,
                            "Pay Date": item.payment_date,
                        }
                        for item in next_month.holdings
                    ]
                )
                st.dataframe(detail, width="stretch", hide_index=True)

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
                pie_event = st.plotly_chart(
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
                bar_event = st.plotly_chart(
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
        """Full-page dividend analysis for one holding."""
        nav_tickers: List[str] = st.session_state.get("portfolio_nav_tickers") or [
            row.ticker for row in rows
        ]
        if not nav_tickers:
            st.session_state["portfolio_view_mode"] = PORTFOLIO_VIEW_OVERVIEW
            st.rerun()

        selected_symbol = st.session_state.get("portfolio_selected_symbol")
        if selected_symbol not in nav_tickers:
            selected_symbol = nav_tickers[0]
            st.session_state["portfolio_selected_symbol"] = selected_symbol

        back_col, title_col, nav_col = st.columns([1, 4, 2])
        with back_col:
            if st.button("← Portfolio", type="primary", use_container_width=True):
                st.session_state["portfolio_view_mode"] = PORTFOLIO_VIEW_OVERVIEW
                st.rerun()
        with title_col:
            st.header(cls._label_for_symbol(rows, selected_symbol))
            charts_ready = len(preload.yield_channels)
            st.caption(
                f"Full holding analysis • {charts_ready} of {len(preload.stock_data)} "
                "holdings have preloaded dividend charts"
            )
        with nav_col:
            selected_symbol = st.selectbox(
                "Holding",
                options=nav_tickers,
                index=nav_tickers.index(selected_symbol),
                format_func=lambda symbol: cls._label_for_symbol(rows, symbol),
                key="portfolio_holding_nav_symbol",
                label_visibility="collapsed",
            )
            st.session_state["portfolio_selected_symbol"] = selected_symbol

        action_col1, action_col2 = st.columns([1, 5])
        with action_col1:
            if st.button("Open in Single Stock", type="secondary", use_container_width=True):
                st.session_state["analysis_type"] = "Single Stock"
                st.session_state["single_stock_symbol"] = selected_symbol
                st.session_state["single_stock_auto_analyze"] = True
                st.rerun()

        if not st.session_state.get("portfolio_analysis_ready"):
            st.info("Reload portfolio details to preload dividend charts for every holding.")
            return

        SingleStockView.render_analysis_for_symbol(
            selected_symbol,
            show_sector=False,
            data=preload.stock_data.get(selected_symbol),
            yield_channel_data=preload.yield_channels.get(selected_symbol),
            vector_doc=preload.vector_docs.get(selected_symbol),
        )

    @classmethod
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
            summary = refresh_portfolio_risks(rows=rows, preload=preload)
        else:
            summary = summary or service.build_summary(rows, preload)

        summary = normalize_attention_summary(summary)
        if summary is None:
            st.warning("Attention data is not available yet. Refresh the risk scan in the sidebar.")
            return

        st.markdown("##### Dividend attention")
        st.caption(
            "Upcoming ex-dates and expected dividend cash this month or next — "
            "informational, not negative risk."
        )
        dividend_df = service.to_dataframe(summary, list_kind="dividend")
        if summary.dividend_total == 0:
            st.success("No upcoming dividend events flagged.")
        else:
            d1, d2 = st.columns(2)
            d1.metric("Dividend events", summary.dividend_total)
            d2.metric("High priority", summary.dividend_high_count)
            cls._render_attention_table(
                rows, dividend_df, table_key="portfolio_dividend_attention_table"
            )

        st.divider()
        st.markdown("##### Attention watchlist")
        st.caption(
            "Negative signals only: expensive yield zones, losses, drawdowns, "
            "weak analyst views, and optional bearish news."
        )
        risk_df = service.to_dataframe(summary, list_kind="risk")

        if summary.total == 0:
            st.success("No negative risk flags right now.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("At risk", summary.total)
            c2.metric("High priority", summary.high_count)
            by_cat = summary.by_category
            c3.metric("Exposure", by_cat.get("Exposure", 0))
            c4.metric("Estimates / news", by_cat.get("Estimates", 0) + by_cat.get("News", 0))
            cls._render_attention_table(
                rows, risk_df, table_key="portfolio_attention_table"
            )

        with st.expander("What triggers each list?"):
            st.markdown(
                """
                **Dividend attention** — ex-date within 3 weeks, or dividend cash
                scheduled / expected this month or next.

                **Attention watchlist** — exposure (yield zone, loss, drawdown),
                estimates (sell ratings, downside to target), and news (when enabled).
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
            "Market cap: **$1B–$10B**, **$10B–$200B**, **> $200B** (source: vector DB / Yahoo)."
        )

        chart_left, chart_right = st.columns(2)
        with chart_left:
            sector_pie = allocation.create_sector_pie(rows)
            if sector_pie:
                st.plotly_chart(
                    sector_pie,
                    width="stretch",
                    key=f"{key_prefix}_sector_pie",
                )
        with chart_right:
            cap_pie = allocation.create_market_cap_pie(rows)
            if cap_pie:
                st.plotly_chart(
                    cap_pie,
                    width="stretch",
                    key=f"{key_prefix}_mcap_pie",
                )

        sector_bar = allocation.create_sector_bar(rows)
        if sector_bar:
            st.plotly_chart(
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
    ) -> None:
        """High-level portfolio dashboard with monthly evolution since inception."""
        service = PortfolioDashboardService()
        deposits = service.list_deposits()
        holdings_snapshot = (
            PortfolioDashboardService.holdings_from_rows(rows) if rows else None
        )
        metrics = service.build_metrics(deposits, holdings=holdings_snapshot)
        summary = metrics.deposits
        evolution = service.evolution_dataframe(deposits)

        cls._render_tab_header("dashboard")

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

        if holdings_snapshot:
            st.markdown("##### Current positions (USD, live)")
            h1, h2, h3, h4, h5 = st.columns(5)
            with h1:
                st.metric("Positions", holdings_snapshot.positions)
            with h2:
                st.metric("Current value", f"${holdings_snapshot.current_value_usd:,.0f}")
            with h3:
                st.metric(
                    "Profit",
                    f"${holdings_snapshot.profit_usd:+,.0f}",
                    f"{holdings_snapshot.profit_pct:+.1f}%"
                    if holdings_snapshot.profit_pct is not None
                    else None,
                )
            with h4:
                st.metric(
                    "Annual dividend income",
                    f"${holdings_snapshot.annual_dividend_income_usd:,.0f}",
                )
            with h5:
                st.metric(
                    "Dividends received",
                    f"${holdings_snapshot.lifetime_dividends_usd:,.0f}",
                )
        else:
            st.info(
                "USD snapshot and dashboard watchlist appear after the portfolio risk scan "
                "in the sidebar (runs on app load)."
            )

        if rows and preload and st.session_state.get("portfolio_analysis_ready"):
            st.divider()
            cls._render_attention_watchlist(rows, preload)

        st.markdown("##### Portfolio evolution (€)")
        evolution_chart = service.create_evolution_chart(deposits)
        if evolution_chart:
            st.plotly_chart(
                evolution_chart,
                width="stretch",
                key="portfolio_dashboard_evolution",
            )

        left, right = st.columns(2)
        with left:
            flow_chart = service.create_monthly_flow_chart(deposits)
            if flow_chart:
                st.plotly_chart(
                    flow_chart,
                    width="stretch",
                    key="portfolio_dashboard_flow",
                )
        with right:
            gain_chart = service.create_gain_chart(deposits)
            if gain_chart:
                st.plotly_chart(
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
            st.plotly_chart(
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
                    st.plotly_chart(
                        end_chart,
                        width="stretch",
                        key="portfolio_yearly_eoy",
                    )
            with y_right:
                dist_chart = benchmark_svc.create_yearly_distribution_chart(yearly_df)
                if dist_chart:
                    st.plotly_chart(
                        dist_chart,
                        width="stretch",
                        key="portfolio_yearly_distribution",
                    )

            ret_chart = benchmark_svc.create_yearly_returns_chart(yearly_df)
            if ret_chart:
                st.plotly_chart(
                    ret_chart,
                    width="stretch",
                    key="portfolio_yearly_returns",
                )

            dep_chart = benchmark_svc.create_yearly_deposits_chart(yearly_df)
            if dep_chart:
                st.plotly_chart(
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
                st.plotly_chart(
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
        cls._render_tab_header("journal")
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
                    st.plotly_chart(
                        treemap,
                        width="stretch",
                        key="purchase_journal_treemap",
                    )
            with t_right:
                lots_pie = service.create_lots_count_pie(records)
                if lots_pie:
                    st.plotly_chart(
                        lots_pie,
                        width="stretch",
                        key="purchase_journal_lots_pie",
                    )

            dual = service.create_dual_split_bar(records)
            if dual:
                st.plotly_chart(dual, width="stretch", key="purchase_journal_dual_bar")

            bubble = service.create_value_vs_lots_chart(records)
            if bubble:
                st.plotly_chart(bubble, width="stretch", key="purchase_journal_bubble")

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
                st.plotly_chart(timeline, width="stretch", key="purchase_journal_timeline")
            left, right = st.columns(2)
            with left:
                yearly = service.create_yearly_activity_chart(records)
                if yearly:
                    st.plotly_chart(yearly, width="stretch", key="purchase_journal_yearly")
            with right:
                price_chart = service.create_price_scatter_by_symbol(records)
                if price_chart:
                    st.plotly_chart(price_chart, width="stretch", key="purchase_journal_prices")

    @classmethod
    def _render_dividend_growth_page(cls) -> None:
        """Annual dividend per share and growth since 2021 for all holdings."""
        cls._render_tab_header("dividend_growth")
        try:
            growth_data = _load_dividend_growth()
        except Exception as exc:
            st.warning(f"Could not load dividend history: {exc}")
            return

        service = PortfolioDividendGrowthService()

        st.markdown(f"##### Overview (since {SINCE_YEAR})")
        st.caption(
            "Annual dividend per share from vector DB. "
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
            st.plotly_chart(
                portfolio_cash,
                width="stretch",
                key="dividend_growth_portfolio_cash",
            )

        heatmap = service.create_annual_heatmap(growth_data)
        if heatmap:
            st.plotly_chart(
                heatmap,
                width="stretch",
                key="dividend_growth_heatmap",
            )

        yoy_heat = service.create_yoy_heatmap(growth_data)
        if yoy_heat:
            st.plotly_chart(
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
                st.plotly_chart(
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
        cls._render_tab_header("dividends")

        if (
            rows
            and preload
            and st.session_state.get("portfolio_analysis_ready")
        ):
            st.markdown("##### 1. Monthly dividend calendar")
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
            "Cash received **after tax**: **10%** withholding through end of 2025, "
            "**16%** from 2026. Estimated gross = Net ÷ (1 − tax rate)."
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
                st.plotly_chart(
                    yearly_chart,
                    width="stretch",
                    key="dividend_income_yearly",
                )
        with chart_right:
            cumulative = service.create_cumulative_chart(records)
            if cumulative:
                st.plotly_chart(
                    cumulative,
                    width="stretch",
                    key="dividend_income_cumulative",
                )

        monthly_chart = service.create_monthly_by_year_chart(records)
        if monthly_chart:
            st.plotly_chart(
                monthly_chart,
                width="stretch",
                key="dividend_income_monthly_years",
            )

        heatmap = service.create_heatmap_chart(records)
        if heatmap:
            st.plotly_chart(
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
        cls._render_tab_header("deposits")
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
            st.plotly_chart(chart, width="stretch", key="portfolio_deposits_timeline")

        cum_chart = service.create_cumulative_chart(deposits)
        if cum_chart:
            st.plotly_chart(cum_chart, width="stretch", key="portfolio_deposits_cumulative")

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
            st.markdown("**Dividends received (from vector DB history)**")
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
        cls._render_tab_header("holdings")
        ready = st.session_state.get("portfolio_analysis_ready", False)
        chart_count = len(preload.yield_channels)
        st.caption(
            f"Loaded {loaded_at.strftime('%Y-%m-%d %H:%M')} · "
            f"{chart_count} yield channels"
            + (" · ready" if ready else "")
        )

        df = cls._rows_to_dataframe(rows, preload)
        cls._render_summary(rows)
        st.divider()

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
                drill_ticker, drill_row, preload, filtered_tickers
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
    def render(cls) -> None:
        st.sidebar.markdown("---")
        st.sidebar.caption(
            "Portfolio data loads automatically with the risk scan (sidebar). "
            "Use **Load Portfolio Details** to force a full reload (~1–2 min)."
        )

        if st.sidebar.button("Load Portfolio Details", type="primary"):
            with st.spinner(
                "Building portfolio table, live prices, and dividend charts for all holdings..."
            ):
                rows, preload = _load_portfolio_payload()
                store_portfolio_payload(rows, preload)
                refresh_portfolio_risks(force=True, rows=rows, preload=preload)

        if st.session_state.get("portfolio_view_mode") == PORTFOLIO_VIEW_HOLDING:
            if "portfolio_details_rows" not in st.session_state:
                st.info(
                    "Portfolio data loads with the sidebar risk scan on app start, "
                    "or use **Load Portfolio Details** to force a reload."
                )
                return
            rows = st.session_state["portfolio_details_rows"]
            preload = _preload_from_session()
            cls._render_holding_focus(rows, preload)
            return

        st.subheader("Portfolio Details")
        with st.expander("What each tab shows", expanded=False):
            for _key, (title, scope) in PORTFOLIO_TAB_SCOPES.items():
                st.markdown(f"**{title}** — {scope}")

        rows_loaded = st.session_state.get("portfolio_details_rows")
        portfolio_preload = (
            _preload_from_session()
            if rows_loaded and st.session_state.get("portfolio_analysis_ready")
            else None
        )
        tab_dashboard, tab_dividends, tab_div_growth, tab_journal, tab_holdings, tab_deposits = st.tabs(
            [
                "Dashboard",
                "Dividends",
                "Dividend growth",
                "Purchase journal",
                "Holdings",
                "Deposits & benchmarks",
            ]
        )

        with tab_dashboard:
            cls._render_dashboard_page(rows_loaded, preload=portfolio_preload)

        with tab_dividends:
            cls._render_dividends_tab(rows_loaded, preload=portfolio_preload)

        with tab_div_growth:
            cls._render_dividend_growth_page()

        with tab_journal:
            cls._render_purchase_journal_page()

        with tab_deposits:
            cls._render_deposits_page()

        with tab_holdings:
            if "portfolio_details_rows" not in st.session_state:
                st.info(
                    "Holdings appear after the sidebar risk scan finishes, "
                    "or click **Load Portfolio Details** to reload."
                )
            else:
                rows = st.session_state["portfolio_details_rows"]
                loaded_at = st.session_state["portfolio_details_time"]
                cls._render_holdings_overview(
                    rows,
                    portfolio_preload or _preload_from_session(),
                    loaded_at,
                )

