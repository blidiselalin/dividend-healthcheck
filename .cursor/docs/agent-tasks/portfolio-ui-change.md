# Task: change portfolio UI behavior

1. Read `.cursor/docs/agents/portfolio-ui.md` and `.cursor/rules/ui-streamlit.mdc`.
2. Identify whether the change is:
   - **Render-only** (display) — edit `ui/*` only
   - **Data/session** — likely `services/portfolio_*` + maybe `ui/*`
   - **DB write** — use `create_portfolio_context()`, then schedule refresh
3. After DB mutations, schedule reload — do **not** call `build_rows_with_cache` synchronously in render paths:
   ```python
   from services.portfolio_refresh import schedule_portfolio_reload
   schedule_portfolio_reload(live_prices=True)
   ```
4. For tests that need immediate session state, use `reload_portfolio_session()` — not in production UI.
5. Verify:
   ```bash
   pytest -m "not integration" -q
   pre-commit run --all-files
   ```

## Streamlit reminders

- Never `with st:` — use `with st.sidebar:` or call widgets directly on the main page.
- Session keys shared across modules: prefer `ui/session_keys.py` to avoid circular imports.
