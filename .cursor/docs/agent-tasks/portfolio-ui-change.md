# Task: change portfolio UI behavior

1. Read `.cursor/docs/agents/portfolio-ui.md` and `.cursor/rules/ui-streamlit.mdc`.
2. **Search first** — grep `ui/` and `services/portfolio_*` for an existing pattern before adding files or helpers.
3. Identify whether the change is:
   - **Render-only** (display) — edit `ui/*` only; no new service module
   - **Data/session** — extend `services/portfolio_*` + minimal `ui/*` wiring
   - **DB write** — use `create_portfolio_context()`, then schedule refresh
4. After DB mutations, schedule reload — do **not** call `build_rows_with_cache` synchronously in render paths:
   ```python
   from services.portfolio_refresh import schedule_portfolio_reload
   schedule_portfolio_reload(live_prices=True)
   ```
5. After **IBKR / broker import** only:
   ```python
   from services.portfolio_refresh import reload_portfolio_after_data_import
   reload_portfolio_after_data_import(section_label="Home")
   ```
6. For tests that need immediate session state, use `reload_portfolio_session()` — not in production UI.
7. If you replace UI behavior, remove dead code or unused session keys in the same change.
8. Verify:
   ```bash
   pytest -m "not integration" -q
   pre-commit run --all-files
   ```

## Streamlit reminders

- Never `with st:` — use `with st.sidebar:` or call widgets directly on the main page.
- Session keys shared across modules: prefer `ui/session_keys.py` to avoid circular imports.
