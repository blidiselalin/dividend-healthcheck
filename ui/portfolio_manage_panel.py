"""
Sidebar UI to add tickers, edit holdings, log purchases/deposits, and refresh portfolio sections.
"""

from __future__ import annotations

from calendar import month_name
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


def _month_label(year: int, month: int) -> str:
    return f"{month_name[int(month)]} {int(year)}"


def _render_monthly_evolution_tab(service: PortfolioManagementService) -> None:
    """Add or edit monthly deposit + portfolio snapshots for the dashboard."""
    st.caption(
        "Record monthly **deposits** and **Portfolio €** for the dashboard evolution table and charts. "
        "Portfolio € must be set for gain and month-over-month columns to appear."
    )

    deposits = service.list_deposits()
    missing_portfolio = service.deposits_missing_portfolio_value()
    if missing_portfolio:
        labels = ", ".join(item.label for item in missing_portfolio[-6:])
        st.warning(
            f"Missing Portfolio €: **{labels}**. Select a month below and enter the end-of-month value."
        )

    period_labels = {"__new__": "Add new month…"}
    period_labels.update(
        {item.period_key: f"{item.label} ({item.period_key})" for item in deposits}
    )
    period_keys = ["__new__"] + [item.period_key for item in deposits]
    if missing_portfolio and st.session_state.get("pm_evo_period", "__new__") == "__new__":
        st.session_state["pm_evo_period"] = missing_portfolio[-1].period_key
    selected = st.selectbox(
        "Month",
        period_keys,
        format_func=lambda key: period_labels[key],
        key="pm_evo_period",
    )

    existing = None
    if selected != "__new__":
        existing = next(item for item in deposits if item.period_key == selected)
        form_key = selected
    else:
        form_key = "new"

    if existing:
        default_year = existing.period.year
        default_month = existing.period.month
        default_label = existing.label
        default_eur = float(existing.deposit_eur)
        default_usd = float(existing.deposit_usd)
        default_port = float(existing.portfolio_eur)
    else:
        default_year = date.today().year
        default_month = date.today().month
        default_label = _month_label(default_year, default_month)
        default_eur = 0.0
        default_usd = 0.0
        default_port = 0.0

    rows = st.session_state.get("portfolio_details_rows") or []
    total_usd = sum(getattr(row, "current_value", 0) or 0.0 for row in rows)
    if total_usd > 0:
        suggested_eur = service.estimate_portfolio_eur_from_usd(total_usd, existing)
        if st.button(
            f"Use live portfolio € ({suggested_eur:,.0f} from ${total_usd:,.0f} holdings)",
            key=f"pm_evo_live_{form_key}",
        ):
            st.session_state[f"pm_evo_port_{form_key}"] = suggested_eur
            st.rerun()

    dep_year = st.number_input(
        "Year",
        min_value=2000,
        max_value=2100,
        value=default_year,
        key=f"pm_evo_year_{form_key}",
    )
    dep_month = st.number_input(
        "Month",
        min_value=1,
        max_value=12,
        value=default_month,
        key=f"pm_evo_month_{form_key}",
    )
    dep_label = st.text_input(
        "Label",
        value=default_label,
        key=f"pm_evo_label_{form_key}",
    )
    dep_eur = st.number_input(
        "Deposit €",
        min_value=0.0,
        value=default_eur,
        step=1.0,
        key=f"pm_evo_eur_{form_key}",
    )
    dep_usd = st.number_input(
        "Deposit $",
        min_value=0.0,
        value=default_usd,
        step=1.0,
        key=f"pm_evo_usd_{form_key}",
    )
    dep_port = st.number_input(
        "Portfolio € (end of month)",
        min_value=0.0,
        value=default_port,
        step=1.0,
        key=f"pm_evo_port_{form_key}",
        help="Required for Monthly evolution gain and MoM % columns on the dashboard.",
    )

    if st.button("Save month", key=f"pm_evo_save_{form_key}"):
        try:
            label = dep_label.strip() or _month_label(int(dep_year), int(dep_month))
            saved = service.add_deposit(
                year=int(dep_year),
                month=int(dep_month),
                label=label,
                deposit_eur=dep_eur,
                deposit_usd=dep_usd,
                portfolio_eur=dep_port,
            )
            msg = f"Saved {saved.label}."
            if saved.portfolio_eur <= 0:
                msg += " Portfolio € is still zero — evolution charts will skip this month."
            _after_change(
                msg,
                full_reload=False,
                sections=["deposits", "dashboard"],
            )
        except Exception as exc:
            st.error(str(exc))


def render_portfolio_manage_sidebar() -> None:
    """Portfolio management expander in the sidebar."""
    service = PortfolioManagementService()

    expand_manage = is_demo_session() or not user_has_holdings_in_db()
    with st.sidebar.expander("Manage portfolio", expanded=expand_manage):
        tab_add, tab_edit, tab_buy, tab_evolution = st.tabs(
            ["Add ticker", "Edit position", "Purchase", "Monthly evolution"]
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
                st.caption(
                    f"Dividends received (auto): **${current.dividends_paid:,.2f}** — "
                    "updated from market history when you reload portfolio data."
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

        with tab_evolution:
            _render_monthly_evolution_tab(service)

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
