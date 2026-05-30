"""
Sidebar UI to add tickers, edit holdings, log purchases/deposits, and refresh portfolio sections.
"""

from __future__ import annotations

from datetime import date
from typing import Callable, Optional

import streamlit as st

from services.portfolio_management_service import PortfolioManagementService
from services.portfolio_refresh import reload_portfolio_session
from services.portfolio_session import is_demo_session, user_has_holdings_in_db


def _after_change(
    message: str,
    *,
    full_reload: bool = True,
    sections: Optional[list[str]] = None,
) -> None:
    from services.portfolio_refresh import invalidate_section_caches

    if full_reload:
        with st.spinner("Updating portfolio views and vector database…"):
            reload_portfolio_session(sections=["all"])
    else:
        invalidate_section_caches(sections or ["journal", "deposits"])
    st.success(message)
    st.rerun()


def render_portfolio_manage_sidebar() -> None:
    """Portfolio management expander in the sidebar."""
    service = PortfolioManagementService()

    expand_manage = is_demo_session() or not user_has_holdings_in_db()
    with st.sidebar.expander("Manage portfolio", expanded=expand_manage):
        tab_add, tab_edit, tab_buy, tab_deposit = st.tabs(
            ["Add ticker", "Edit position", "Purchase", "Deposit"]
        )

        with tab_add:
            st.caption("Adds a holding to your portfolio and fetches market data into the shared library.")
            symbol = st.text_input("Ticker", key="pm_add_symbol", placeholder="e.g. VZ")
            shares = st.number_input("Shares", min_value=0.0, value=10.0, step=1.0, key="pm_add_shares")
            avg_cost = st.number_input(
                "Avg cost / share (USD)",
                min_value=0.0,
                value=0.0,
                step=0.01,
                key="pm_add_avg",
            )
            commission = st.number_input(
                "Commission (USD)",
                min_value=0.0,
                value=0.0,
                step=0.01,
                key="pm_add_comm",
            )
            div_paid = st.number_input(
                "Dividends received (USD)",
                min_value=0.0,
                value=0.0,
                step=0.01,
                key="pm_add_div",
            )
            company = st.text_input(
                "Company name (optional)",
                key="pm_add_company",
                help="Filled from Yahoo Finance if left blank.",
            )
            skip_check = st.checkbox("Skip Yahoo validation", key="pm_add_skip")
            if st.button("Add to portfolio", type="primary", key="pm_add_btn"):
                try:
                    if shares <= 0:
                        st.error("Shares must be greater than zero.")
                    elif avg_cost <= 0 and not skip_check:
                        st.error("Enter average cost per share.")
                    else:
                        result = service.add_ticker(
                            symbol,
                            shares=shares,
                            avg_cost_per_share=avg_cost or 0.01,
                            commission=commission,
                            dividends_paid=div_paid,
                            company_name=company.strip() or None,
                            skip_validation=skip_check,
                        )
                        sync = result.get("vector_sync") or {}
                        created = sync.get("created", 0)
                        msg = f"Added {result['symbol']}."
                        if created:
                            msg += " New analysed stocks document created."
                        _after_change(msg)
                except ValueError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Could not add ticker: {exc}")

        holdings = service.list_holdings()
        symbols = [h.symbol for h in holdings]

        with tab_edit:
            if not symbols:
                st.info("No holdings yet. Add a ticker first.")
            else:
                pick = st.selectbox("Position", symbols, key="pm_edit_symbol")
                current = next(h for h in holdings if h.symbol == pick)
                new_shares = st.number_input(
                    "Shares",
                    min_value=0.0,
                    value=float(current.shares),
                    step=1.0,
                    key="pm_edit_shares",
                )
                new_avg = st.number_input(
                    "Avg cost / share",
                    min_value=0.0,
                    value=float(current.avg_cost_per_share),
                    step=0.01,
                    key="pm_edit_avg",
                )
                new_comm = st.number_input(
                    "Commission",
                    min_value=0.0,
                    value=float(current.commission),
                    step=0.01,
                    key="pm_edit_comm",
                )
                new_div = st.number_input(
                    "Dividends received",
                    min_value=0.0,
                    value=float(current.dividends_paid),
                    step=0.01,
                    key="pm_edit_div",
                )
                new_company = st.text_input(
                    "Company name",
                    value=current.company_name or "",
                    key="pm_edit_company",
                )
                col_save, col_del = st.columns(2)
                with col_save:
                    if st.button("Save changes", key="pm_edit_save"):
                        try:
                            service.update_holding_fields(
                                pick,
                                shares=new_shares,
                                avg_cost_per_share=new_avg,
                                commission=new_comm,
                                dividends_paid=new_div,
                                company_name=new_company.strip() or None,
                            )
                            _after_change(f"Updated {pick}.")
                        except Exception as exc:
                            st.error(str(exc))
                with col_del:
                    if st.button("Remove", key="pm_edit_remove"):
                        if service.remove_ticker(pick):
                            _after_change(f"Removed {pick}.")
                        else:
                            st.error("Could not remove position.")

        with tab_buy:
            if not symbols:
                st.info("Add a holding before logging purchases.")
            else:
                buy_symbol = st.selectbox("Ticker", symbols, key="pm_buy_symbol")
                buy_date = st.date_input("Purchase date", value=date.today(), key="pm_buy_date")
                buy_price = st.number_input(
                    "Price (USD)",
                    min_value=0.0,
                    value=0.0,
                    step=0.01,
                    key="pm_buy_price",
                )
                if st.button("Log purchase", key="pm_buy_btn"):
                    try:
                        service.add_purchase(buy_symbol, buy_date, buy_price)
                        _after_change(
                            f"Logged purchase for {buy_symbol}.",
                            full_reload=False,
                            sections=["journal"],
                        )
                    except ValueError as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        st.error(str(exc))

        with tab_deposit:
            dep_year = st.number_input("Year", min_value=2000, max_value=2100, value=date.today().year)
            dep_month = st.number_input("Month", min_value=1, max_value=12, value=date.today().month)
            dep_label = st.text_input("Label", value=date.today().strftime("%B %Y"))
            dep_eur = st.number_input("Deposit EUR", min_value=0.0, value=0.0, step=1.0)
            dep_usd = st.number_input("Deposit USD", min_value=0.0, value=0.0, step=1.0)
            dep_port = st.number_input("Portfolio EUR", min_value=0.0, value=0.0, step=1.0)
            if st.button("Save month", key="pm_dep_btn"):
                try:
                    service.add_deposit(
                        year=int(dep_year),
                        month=int(dep_month),
                        label=dep_label.strip() or f"{int(dep_year)}-{int(dep_month):02d}",
                        deposit_eur=dep_eur,
                        deposit_usd=dep_usd,
                        portfolio_eur=dep_port,
                    )
                    _after_change(
                        "Deposit saved.",
                        full_reload=False,
                        sections=["deposits"],
                    )
                except Exception as exc:
                    st.error(str(exc))


def render_tab_refresh_button(
    section: str,
    *,
    on_refresh: Optional[Callable[[], None]] = None,
) -> None:
    """Small Update control aligned with tab headers."""
    from services.portfolio_refresh import make_section_refresher

    callback = on_refresh or make_section_refresher(section)
    if st.button("Update", key=f"portfolio_refresh_{section}", help="Reload this tab with latest data"):
        callback()
