# DividendScope beta validation

Validation date: 2026-11-12.

This file records what was inspected and which checks were executed. A test file on disk is not a pass. An unexecuted check is **Not run**.

## Baseline

| Item | Result |
|---|---|
| HEAD | `930fef8e7dfef4c765498cf7b8008f592e9375f9` ("What is real", 2026-08-14) |
| Branch | `main`, tracking `origin/main`, equal to `origin/main` |
| Tags | None |
| Commits since 2026-06-01 | 213. No commit after 2026-08-14. October–November work is the uncommitted working tree, not a commit |
| Unmerged remote | `origin/copilot/update-readme-organize-changes` (README only). Not part of this candidate |
| Working tree | Dirty. `.gitignore`, import/cash/replace/allocation services, their tests, two UI files, plus untracked `docs/implementation-roadmap.md` |
| `git diff --check` | Pass, on that dirty tree |
| Python used for executed tests | 3.15.2 at `.venv/bin/python`. `chromadb` is not installed: `onnxruntime` has no 3.15 wheel |
| CI interpreters | `.github/workflows/tests.yml` and `lint.yml` use Python 3.11 and 3.12. Those jobs were not executed on this tree |
| Postgres | `psql` and `docker` are not on PATH here. Integration tests were not run |
| Requirement register | `docs/implementation-roadmap.md` |

There is no immutable release SHA. Every pass below is against the dirty working tree based on `930fef8`, not against a tag.

## Beta capabilities

| Capability | Status | Code | Tests | This validation |
|---|---|---|---|---|
| Public sample portfolio | Implemented but untested | `services/guest_playground.py` | `tests/test_guest_playground.py` | Not run |
| Google sign-in and allowlist | Implemented but untested | `auth/user_context.py`, access-request UI | `tests/test_auth.py`, `tests/test_access_requests.py` | Not run |
| Manual holding | Implemented but untested | portfolio store and manage UI | portfolio service tests | Not run |
| Supported IBKR CSV import | Partially implemented | `services/ibkr_activity_parser.py`, `services/portfolio_broker_import_service.py` | `tests/test_ibkr_activity_parser.py`, `tests/test_portfolio_broker_import.py` | See financial section. 2022 file is missing |
| MERGE does not clear the book | Verified implemented | `apply_import` | `test_merge_import_never_calls_clear_user_portfolio` and the 49-test run below | Pass on the tree at 2026-11-12 09:31Z. The tree changed later |
| REPLACE failure restores the book | Verified implemented | `services/portfolio_clear_service.py` | `test_replace_failure_after_clear_restores_previous_portfolio`, `test_killed_replace_restores_on_next_open` | Pass, Python 3.15.2, after the recovery-file edit |
| Received gross and net follow posted receipts | Verified implemented | `services/portfolio_month_dividends.py`, `services/portfolio_dividend_cash.py` | `tests/test_portfolio_dividend_cash.py`, month-card tests | Pass on the focused runs cited below |
| Open-holding month card | Verified implemented | month card in `ui/portfolio_details_view.py` | `test_current_month_card_uses_open_holdings_only` | Pass in the 49-test run. Caption was edited before that run |
| Missing quarter is not a fake zero | Verified implemented | `services/portfolio_dividend_quarters.py` | `test_missing_quarter_is_not_reported_as_zero` | Pass after the edit. 4 passed, Python 3.15.2 |
| Unpriced holding excluded from allocation weights | Verified implemented | `services/portfolio_allocation_service.py` | `test_unpriced_holding_is_excluded_from_sector_weights` | Pass in that same 4-test run |
| 2022–2026 broker reconciliation | Missing | Owner constants in `services/portfolio_dividend_quarters.py`, flagged `IBKR_REFERENCE_OWNER_ONLY` | `tests/test_portfolio_dividend_quarters.py` compares numbers when a reference is passed in. No anonymized 2022–2026 statement fixture | Blocked. Do not treat the constants as a reconciliation |
| 2024-style CSV parse | Implemented but untested in this gate | `tests/fixtures/ibkr_activity_2024_style.csv` | `test_parse_2024_style_export` | Not run in this gate |
| Dividend health / risk | Implemented but untested in this gate | `services/clear_dividend_risk.py` methodology 1.2 | `tests/test_clear_dividend_risk.py` | Not run |
| Research and scoring | Partially implemented | `services/scoring.py` | `tests/test_scoring_service.py` | Not run. This is not the missing screener |
| Provenance labels | Partially implemented | `services/analysis_evidence.py` | `tests/test_analysis_evidence.py` | Not run |
| Support, privacy, security pages | Partially implemented | `SECURITY.md`, `PRIVACY.md`, `TERMS.md`, `SUPPORT.md` | — | Inspected. Owner placeholders are still `[OWNER ACTION REQUIRED: …]` |
| Per-user isolation | Implemented but untested in this gate | `user_id` on portfolio rows | `tests/test_auth.py`, `tests/integration/test_postgres_live.py` | Unit auth not run. Postgres integration not run |
| Backup, restore, rollback | Partially implemented | In-process and killed-process replace recovery only | `tests/test_portfolio_clear_service.py` | Replace recovery passed. No Postgres backup was taken or restored |
| Automatic IBKR sync, trading, payments, public real portfolios | Out of scope for beta | Excluded in `docs/releases/BETA_SCOPE.md` | — | Not started, as required |

## Financial checks executed

Environment for every command: Python 3.15.2, `.venv`, working tree on `930fef8`, Chroma not installed.

| Command | When | Result |
|---|---|---|
| `pytest` on `test_replace_failure_after_clear_restores_previous_portfolio`, merge-does-not-clear, preview, clear service, dividend cash, and three month tests | Before the recovery-file and quarter edits | 13 passed |
| `test_apply_import_without_open_positions` and `test_merge_same_file_twice_is_idempotent` | Same tree generation | 2 passed in 260.40s. The time is month-end price backfill |
| `pytest tests/test_portfolio_broker_import.py tests/test_portfolio_clear_service.py tests/test_portfolio_dividend_cash.py tests/test_portfolio_month_dividends.py` | Started 2026-11-12T09:31:06Z, finished 10:06:34Z | 49 passed in 2126.76s. The working tree was edited while this process was running. Do not use it as coverage of the later quarter, allocation, or recovery-file code |
| `pytest tests/test_portfolio_clear_service.py`, `test_missing_quarter_is_not_reported_as_zero`, `test_unpriced_holding_is_excluded_from_sector_weights` | After those edits | 4 passed |
| `pytest tests/ -q -m "not integration"` | Started 2026-11-12T10:17:32Z, finished 11:00:20Z, exit 1, 2568.56s | Fail. 864 collected. 11 failed: 8 command-center guest/import tests (`session_state` had no `guest_playground_holdings`, or `assert False`), 2 market-library tests (`No module named 'chromadb'`), and `test_estimate_history_years_from_library` (`assert 6 == 5`). Skips appear on the progress line. 13 integration tests were not included |

Not recreated, because the source is not in the repo:

- 2022 IBKR activity CSV
- Anonymized 2022–2026 monthly gross, withholding, and net fixtures
- Like-for-like reconciliation to the cent against a broker statement

Overlapping years, repeated import, reversals, closed positions, and deposits are covered by tests in `tests/test_portfolio_broker_import.py`. Those tests passed in the 49-test run above. Corrections that change an amount under a new identity (IMP-006) and non-USD stock rows (IMP-010) remain partial. Realized P&L and total return are not defined. Historical valuation still needs a "no price" state rather than a silent zero (FIN-005); that test file was not run in this gate.

## Journeys

Journeys A–D were not executed. No staging URL is running, and Google OAuth was not exercised. Browser checks of the income and allocation captions were not done.

## Phase 4 dispositions

| Enhancement | Disposition |
|---|---|
| Sector weights from current price | Include. Validated by `test_unpriced_holding_is_excluded_from_sector_weights` |
| Company and dividend-income concentration | Include only as the existing Clear Dividend Risk alerts. `tests/test_clear_dividend_risk.py` was not run in this gate |
| Configurable allocation targets | Defer. Post-beta. No target store. Do not show "underweight" |
| Portfolio-aware discovery | Defer. Post-beta |
| Dividend-growth screener, yield ≤ 3%, materials top 2 / top 5 | Defer. The original prompt is not in the repo. Do not describe a screener as available |
| Ranking and provenance | Include the existing score breakdown and evidence helpers. Not re-validated in this gate |
| Updated research prompt | Remove unsupported claims. No prompt file exists |
| Optional hosted model | Include only as the existing FAQ, which works with the model disabled. Local models stay deferred. Payload isolation was not re-tested |
| Demo and onboarding | Include. Guest tests were not run in this gate. Sample data must stay labeled |
| Investor presentation | Defer. `docs/product/dividendscope_launch_pitch_demo.html` was not checked against verified behavior |
| Cursor rules and `AGENTS.md` | Include. They are the working conventions. Not a product feature |

## Phase 5 gates

| Gate | Status |
|---|---|
| `git diff --check` | Pass |
| `pre-commit run --all-files` | Not run. Not started while the unit suite was using the tree |
| `pytest -m "not integration"` | Fail. 11 failed in 2568.56s on Python 3.15.2. See the financial section |
| `python -m db --migrate` and `pytest -m integration` on Postgres 16 | Blocked. No local Postgres client or Docker |
| Python 3.11 and 3.12 CI jobs | Not run |
| Clean install, schema upgrade, backup restore, rollback rehearsal | Not run, except the in-app replace recovery tests |
| Auth, secrets, dependency review, HTTPS, performance, responsive UI | Not run |
