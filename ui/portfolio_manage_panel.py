"""
Sidebar UI to add tickers, edit holdings, log purchases/deposits, and refresh portfolio sections.
"""

from __future__ import annotations

from calendar import month_name
from datetime import date
from typing import Callable

import streamlit as st

from services.portfolio_management_service import PortfolioManagementService
from services.portfolio_refresh import schedule_portfolio_reload
from services.portfolio_session import is_demo_session, user_has_holdings_in_db


def _after_change(
    message: str,
    *,
    full_reload: bool = True,
    sections: list[str] | None = None,
) -> None:
    from services.portfolio_session import invalidate_holdings_cache

    invalidate_holdings_cache()
    if full_reload:
        schedule_portfolio_reload(live_prices=False, sections=sections or ["all"])
        st.success(f"{message} Updating views in the background.")
    else:
        from services.portfolio_refresh import invalidate_section_caches

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

    st.number_input(
        "Year",
        min_value=2000,
        max_value=2100,
        value=default_year,
        key=f"pm_evo_year_{form_key}",
    )
    st.number_input(
        "Month",
        min_value=1,
        max_value=12,
        value=default_month,
        key=f"pm_evo_month_{form_key}",
    )
    st.text_input(
        "Label",
        value=default_label,
        key=f"pm_evo_label_{form_key}",
    )
    st.number_input(
        "Deposit €",
        min_value=0.0,
        value=default_eur,
        step=1.0,
        key=f"pm_evo_eur_{form_key}",
    )
    st.number_input(
        "Deposit $",
        min_value=0.0,
        value=default_usd,
        step=1.0,
        key=f"pm_evo_usd_{form_key}",
    )
    st.number_input(
        "Portfolio € (end of month)",
        min_value=0.0,
        value=default_port,
        step=1.0,
        key=f"pm_evo_port_{form_key}",
        help="Required for Monthly evolution gain and MoM % columns on the dashboard.",
    )

    if st.button("Save month", key=f"pm_evo_save_{form_key}"):
        try:
            year_val = int(st.session_state[f"pm_evo_year_{form_key}"])
            month_val = int(st.session_state[f"pm_evo_month_{form_key}"])
            label = st.session_state[f"pm_evo_label_{form_key}"].strip() or _month_label(
                year_val, month_val
            )
            saved = service.add_deposit(
                year=year_val,
                month=month_val,
                label=label,
                deposit_eur=st.session_state[f"pm_evo_eur_{form_key}"],
                deposit_usd=st.session_state[f"pm_evo_usd_{form_key}"],
                portfolio_eur=st.session_state[f"pm_evo_port_{form_key}"],
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
        if (
            st.session_state.get("portfolio_onboarding_show_manage_tip")
            and not user_has_holdings_in_db()
        ):
            st.info(
                "**Step 1:** Add ticker tab below — symbol, shares, average cost, then "
                "**Add to portfolio**. Views refresh in the background automatically."
            )
        tab_add, tab_edit, tab_buy, tab_evolution, tab_ibkr = st.tabs(
            ["Add ticker", "Edit position", "Purchase", "Monthly evolution", "Import IBKR"]
        )

        with tab_add:
            st.caption(
                "Adds a holding to your portfolio and fetches market data into the shared library."
            )
            st.text_input("Ticker", key="pm_add_symbol", placeholder="e.g. VZ")
            st.number_input("Shares", min_value=0.0, value=10.0, step=1.0, key="pm_add_shares")
            st.number_input(
                "Avg cost / share (USD)",
                min_value=0.0,
                value=0.0,
                step=0.01,
                key="pm_add_avg",
            )
            st.number_input(
                "Commission (USD)",
                min_value=0.0,
                value=0.0,
                step=0.01,
                key="pm_add_comm",
            )
            st.text_input(
                "Company name (optional)",
                key="pm_add_company",
                help="Filled from Yahoo Finance if left blank.",
            )
            st.checkbox("Skip Yahoo validation", key="pm_add_skip")
            if st.button("Add to portfolio", type="primary", key="pm_add_btn"):
                try:
                    if st.session_state.pm_add_shares <= 0:
                        st.error("Shares must be greater than zero.")
                    elif st.session_state.pm_add_avg <= 0 and not st.session_state.pm_add_skip:
                        st.error("Enter average cost per share.")
                    else:
                        result = service.add_ticker(
                            st.session_state.pm_add_symbol,
                            shares=st.session_state.pm_add_shares,
                            avg_cost_per_share=st.session_state.pm_add_avg or 0.01,
                            commission=st.session_state.pm_add_comm,
                            company_name=(st.session_state.pm_add_company.strip() or None),
                            skip_validation=st.session_state.pm_add_skip,
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
                previous_pick = st.session_state.get("pm_edit_symbol_prev")
                if previous_pick != pick:
                    st.session_state["pm_edit_shares"] = float(current.shares)
                    st.session_state["pm_edit_avg"] = float(current.avg_cost_per_share)
                    st.session_state["pm_edit_comm"] = float(current.commission)
                    st.session_state["pm_edit_company"] = current.company_name or ""
                    st.session_state["pm_edit_symbol_prev"] = pick
                new_shares = st.number_input(
                    "Shares",
                    min_value=0.0,
                    value=float(st.session_state.get("pm_edit_shares", current.shares)),
                    step=1.0,
                    key="pm_edit_shares",
                )
                new_avg = st.number_input(
                    "Avg cost / share",
                    min_value=0.0,
                    value=float(st.session_state.get("pm_edit_avg", current.avg_cost_per_share)),
                    step=0.01,
                    key="pm_edit_avg",
                )
                new_comm = st.number_input(
                    "Commission",
                    min_value=0.0,
                    value=float(st.session_state.get("pm_edit_comm", current.commission)),
                    step=0.01,
                    key="pm_edit_comm",
                )
                st.caption(
                    f"Dividends received (auto): **${current.dividends_paid:,.2f}** — "
                    "updated from market history when you reload portfolio data."
                )
                new_company = st.text_input(
                    "Company name",
                    value=st.session_state.get("pm_edit_company", current.company_name or ""),
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
                st.caption(
                    "Log a buy with share count and commission. "
                    "Your position totals update automatically."
                )
                st.selectbox("Ticker", symbols, key="pm_buy_symbol")
                st.date_input("Purchase date", value=date.today(), key="pm_buy_date")
                st.number_input(
                    "Shares",
                    min_value=0.0,
                    value=0.0,
                    step=1.0,
                    key="pm_buy_shares",
                )
                st.number_input(
                    "Price per share (USD)",
                    min_value=0.0,
                    value=0.0,
                    step=0.01,
                    key="pm_buy_price",
                )
                st.number_input(
                    "Commission (USD)",
                    min_value=0.0,
                    value=0.0,
                    step=0.01,
                    key="pm_buy_commission",
                    help="Broker fee for this purchase, separate from the share price.",
                )
                if st.button("Log purchase", key="pm_buy_btn"):
                    try:
                        shares = float(st.session_state.pm_buy_shares)
                        price = float(st.session_state.pm_buy_price)
                        commission = float(st.session_state.pm_buy_commission)
                        if shares <= 0:
                            st.error("Shares must be greater than zero.")
                        elif price <= 0:
                            st.error("Price per share must be greater than zero.")
                        else:
                            service.add_purchase(
                                st.session_state.pm_buy_symbol,
                                st.session_state.pm_buy_date,
                                price,
                                shares=shares,
                                commission_usd=commission,
                            )
                            _after_change(
                                f"Logged purchase for {st.session_state.pm_buy_symbol} "
                                f"({shares:g} shares).",
                                full_reload=True,
                            )
                    except ValueError as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        st.error(str(exc))

        with tab_ibkr:
            _render_ibkr_import_tab()


def _render_ibkr_import_tab() -> None:
    """Upload IBKR Activity Statement CSV and merge or replace portfolio data."""
    from services.ibkr_activity_parser import ImportIssueLevel, has_blocking_errors
    from services.portfolio_broker_import_service import ImportMode, apply_import, preview_import

    if is_demo_session():
        st.info("IBKR import is disabled for the demo account.")
        return

    st.caption(
        "Import an **Interactive Brokers Activity Statement** CSV (AS_Fv2). "
        "Holdings, trades, and cash dividends are loaded from Open Positions, Trades, "
        "and Dividends sections."
    )
    uploaded = st.file_uploader(
        "Activity Statement CSV",
        type=["csv"],
        key="pm_ibkr_file",
    )
    if uploaded is not None:
        st.session_state["pm_ibkr_file_content"] = uploaded.getvalue()
        st.session_state["pm_ibkr_file_name"] = uploaded.name

    content = st.session_state.get("pm_ibkr_file_content")
    if not content:
        return

    mode_label = st.radio(
        "Import mode",
        ["Merge with existing", "Full replace"],
        key="pm_ibkr_mode",
        help=(
            "**Merge** updates only symbols in the file (prior IBKR rows for those symbols are "
            "replaced). **Full replace** deletes all portfolio data first."
        ),
    )
    replace_mode = mode_label == "Full replace"
    if replace_mode:
        st.warning(
            "Full replace permanently deletes all holdings, purchases, dividends, deposits, "
            "and monthly totals before importing."
        )
        st.checkbox(
            "I understand this deletes all portfolio data",
            key="pm_ibkr_replace_confirm",
        )

    file_name = st.session_state.get("pm_ibkr_file_name")
    if file_name:
        st.caption(f"Loaded file: **{file_name}**")

    preview = preview_import(content)
    meta = preview.meta
    if meta.account or meta.period:
        st.markdown(f"**Account:** {meta.account or '—'} · **Period:** {meta.period or '—'}")
    st.markdown(
        f"**{preview.position_count}** positions · **{preview.trade_count}** stock trades · "
        f"**{preview.dividend_count}** dividends"
    )
    if preview.forex_trades_skipped:
        st.caption(
            f"{preview.forex_trades_skipped} FX currency trades in the file were skipped "
            "(only USD stock trades import)."
        )
    if preview.symbols:
        st.caption("Symbols: " + ", ".join(preview.symbols))

    for issue in preview.issues:
        if issue.level == ImportIssueLevel.ERROR:
            st.error(issue.message)
        elif issue.level == ImportIssueLevel.WARNING:
            st.warning(issue.message)
        else:
            st.info(issue.message)

    apply_disabled = preview.blocking or (
        replace_mode and not st.session_state.get("pm_ibkr_replace_confirm")
    )
    if st.button("Apply import", type="primary", key="pm_ibkr_apply", disabled=apply_disabled):
        mode = ImportMode.REPLACE if replace_mode else ImportMode.MERGE
        try:
            result = apply_import(content, mode=mode)
        except Exception as exc:
            st.error(f"Import failed: {exc}")
            return
        if has_blocking_errors(result.issues):
            st.error("Import blocked by validation errors.")
            return
        if result.holdings_upserted == 0:
            st.error("Import did not write any holdings.")
            return
        st.session_state.pop("pm_ibkr_file_content", None)
        st.session_state.pop("pm_ibkr_file_name", None)
        msg = (
            f"IBKR import ({result.mode.value}): {result.holdings_upserted} holdings, "
            f"{result.trades_imported} stock trades, {result.dividends_imported} dividends."
        )
        from services.portfolio_refresh import reload_portfolio_after_data_import

        reload_portfolio_after_data_import(section_label="Home", refresh_risks=True)
        st.success(msg)
        st.rerun()


def render_tab_refresh_button(
    section: str,
    *,
    on_refresh: Callable[[], None] | None = None,
) -> None:
    """Small Update control aligned with tab headers."""
    from services.portfolio_refresh import make_section_refresher

    callback = on_refresh or make_section_refresher(section)
    if st.button(
        "Update", key=f"portfolio_refresh_{section}", help="Reload this tab with latest data"
    ):
        callback()
