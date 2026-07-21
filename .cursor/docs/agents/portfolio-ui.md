# Portfolio UI session (agent deep dive)

Do **not** block Streamlit reruns with synchronous portfolio rebuilds in `ui/*`.

## Module map

| Concern | Module | Pattern |
|---------|--------|---------|
| DB changed since last load | `services/portfolio_session.py` | `compute_portfolio_db_fingerprint()` → `schedule_portfolio_refresh()` |
| Fast startup | `services/portfolio_ui_cache.py` | `hydrate_session_from_disk()`; stale cache schedules `warm_portfolio` |
| User-triggered reload | `services/portfolio_refresh.py` | `schedule_portfolio_reload(live_prices=…)` |
| Apply job results | `services/deferred_startup.py` | `apply_background_results()` on main thread only |
| Tests needing sync rebuild | `services/portfolio_refresh.py` | `reload_portfolio_session()` — **not** for production UI |

Fingerprint tables: `holdings`, `purchase_journal`, `monthly_deposits`, `dividend_receipts`, `net_dividends` (`utils/portfolio_db.py`).

## New-user onboarding

- Steps: `services/portfolio_onboarding.py`
- UI: `ui/portfolio_onboarding.py`
- Align copy with background-job flow and `PORTFOLIO_NAV` section hints in `ui/theme.py`

## Chatbot

- UI: `ui/chatbot_widget.py` — sidebar Assistant expander
- Logic: `services/chatbot_service.py` — FAQ first, optional Hugging Face server-side
- Do **not** call inference APIs from `components.html` / browser JS
- Disable UI: `DIVIDENDSCOPE_CHATBOT_ENABLED=0`
- Tests: `tests/test_chatbot_service.py`
