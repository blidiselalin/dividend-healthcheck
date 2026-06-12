"""
Admin database validation and read-only SQL explorer.
"""

from __future__ import annotations

import streamlit as st

from auth.user_context import is_app_admin
from services.db_admin_service import (
    inspect_stock_symbol,
    list_managed_tables,
    preset_queries,
    run_readonly_query,
    sample_stock_documents_issues,
    sample_table_rows,
    storage_label,
    table_row_counts,
    validate_all_tables,
)
from ui.theme import render_notice


def render_database_admin_tabs() -> None:
    """Database admin tabs (embedded in the admin console)."""
    if not is_app_admin():
        render_notice("Admin access required.", kind="warning")
        return

    st.caption(f"Storage: **{storage_label()}** — read-only validation and SELECT queries.")

    tab_overview, tab_tables, tab_symbol, tab_sql = st.tabs(
        ["Overview", "Tables", "Symbol probe", "SQL explorer"]
    )

    with tab_overview:
        _render_overview_tab()

    with tab_tables:
        _render_tables_tab()

    with tab_symbol:
        _render_symbol_tab()

    with tab_sql:
        _render_sql_tab()


def _render_overview_tab() -> None:
    if st.button("Run validation", key="admin_db_validate"):
        st.session_state["admin_db_checks"] = validate_all_tables()
        st.rerun()

    checks = st.session_state.get("admin_db_checks")
    if checks is None:
        render_notice(
            "Click **Run validation** to check row counts and library coverage across all tables.",
            kind="info",
        )
        return

    rows = []
    for check in checks:
        rows.append(
            {
                "Table": check.name,
                "Status": "OK" if check.ok else "Check",
                "Rows": check.row_count if check.row_count >= 0 else "—",
                "Summary": check.message,
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)

    issues = sample_stock_documents_issues(limit=25)
    if issues:
        st.subheader("Thin library symbols (sample)")
        st.caption("Tickers with fewer than 252 price points or fewer than 4 dividend payments.")
        st.dataframe(issues, width="stretch", hide_index=True)


def _render_tables_tab() -> None:
    tables = list_managed_tables()
    if not tables:
        render_notice("No tables found in the configured database.", kind="info")
        return

    counts = table_row_counts(tables)
    rows = [{"Table": name, "Rows": counts.get(name, "—")} for name in tables]
    st.dataframe(rows, width="stretch", hide_index=True)

    pick = st.selectbox("Inspect table", options=tables, key="admin_db_table_pick")
    if st.button(f"Sample rows from {pick}", key="admin_db_table_sample"):
        result = sample_table_rows(pick, allowed_tables=tables, limit=50)
        st.session_state["admin_db_last_result"] = result
        st.session_state["admin_db_last_sql"] = f"SELECT * FROM {pick}"  # noqa: S608

    last = st.session_state.get("admin_db_last_result")
    if last and last.ok and last.rows:
        st.caption(st.session_state.get("admin_db_last_sql", ""))
        st.dataframe(last.rows, width="stretch", hide_index=True)
    elif last and not last.ok:
        st.error(last.message)


def _render_symbol_tab() -> None:
    symbol = st.text_input("Ticker symbol", value="INTU", key="admin_db_symbol").strip().upper()
    if st.button("Inspect symbol", key="admin_db_symbol_run") and symbol:
        st.session_state["admin_db_symbol_result"] = inspect_stock_symbol(symbol)

    result = st.session_state.get("admin_db_symbol_result")
    if not result:
        render_notice(
            "Enter a symbol (e.g. INTU, ABBV) to verify price and dividend history in the library.",
            kind="info",
        )
        return

    if not result.get("ok"):
        st.warning(result.get("message", "Check failed"))
    else:
        st.success(result.get("message", "OK"))

    display = {k: v for k, v in result.items() if k not in ("ok", "message")}
    st.json(display)


def _render_sql_tab() -> None:
    from db.connection import use_cloud_sql

    presets = preset_queries()
    if not use_cloud_sql():
        presets = {
            name: sql
            for name, sql in presets.items()
            if "jsonb" not in sql and "::bigint" not in sql
        }
    preset_name = st.selectbox(
        "Preset query",
        options=["(custom)", *list(presets.keys())],
        key="admin_db_preset",
    )
    if preset_name != "(custom)":
        preset_sql = presets[preset_name]
        st.session_state["admin_db_sql_draft"] = preset_sql
        st.session_state["admin_db_sql_input"] = preset_sql
    elif "admin_db_sql_input" not in st.session_state:
        st.session_state["admin_db_sql_input"] = st.session_state.get("admin_db_sql_draft", "")
    sql = st.text_area(
        "SELECT query",
        height=220,
        key="admin_db_sql_input",
        placeholder="SELECT symbol, last_updated FROM stock_documents LIMIT 10",
    )
    row_limit = st.slider(
        "Max rows", min_value=10, max_value=500, value=200, key="admin_db_row_limit"
    )

    if st.button("Run query", key="admin_db_sql_run", type="primary"):
        st.session_state["admin_db_sql_draft"] = sql
        st.session_state["admin_db_sql_result"] = run_readonly_query(sql, row_limit=row_limit)

    result = st.session_state.get("admin_db_sql_result")
    if result is None:
        render_notice(
            "Only read-only SELECT queries are allowed. Destructive SQL is blocked.", kind="info"
        )
        return

    if not result.ok:
        st.error(result.message)
        return

    st.caption(result.message + (" — results truncated" if result.truncated else ""))
    if result.rows:
        st.dataframe(result.rows, width="stretch", hide_index=True)
    else:
        st.info("Query returned no rows.")
