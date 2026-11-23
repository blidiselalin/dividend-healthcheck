# DividendScope v0.1.0-beta.1 release report

Date: 2026-11-12.

Candidate: dirty working tree on `930fef8e7dfef4c765498cf7b8008f592e9375f9`. No tag. `origin/main` is that same commit. October–November financial work is uncommitted.

Environment for executed tests: Python 3.15.2 (`.venv`). Chroma is not installed on this interpreter. CI remains Python 3.11 and 3.12, and those jobs were not run.

Detail and the requirement matrix: `docs/releases/BETA_VALIDATION.md`. The June–November register: `docs/implementation-roadmap.md`.

## A. Implementation coverage

| Beta requirement | Implemented | Code | Tests | Remaining issue |
|---|---|---|---|---|
| Public demo on sample data | Yes | `services/guest_playground.py` | `tests/test_guest_playground.py` | Not executed in this gate |
| Google sign-in, invite-only real portfolios | Yes | `auth/user_context.py` | `tests/test_auth.py`, `tests/test_access_requests.py` | Not executed. Live OAuth not opened |
| Manual holdings and supported CSV import | Partial | `services/portfolio_broker_import_service.py` | Broker-import suite | 2022 layout has no fixture. Non-USD stocks and corrected identities are partial |
| MERGE and REPLACE | Yes | `apply_import`, `portfolio_clear_service.py` | Replace-failure and killed-process tests passed | Recovery is an app file, not a database backup |
| Received vs estimated dividends | Partial | Month resolver and income captions | Cash and month tests passed | Other screens were not all rewritten. Browser not checked |
| 2022–2026 broker reconciliation | No | Owner-only constants | No anonymized statement fixture | Blocked. Product UI no longer claims a match |
| Holdings, allocation, missing prices | Partial | `portfolio_allocation_service.py` | Unpriced-weight test passed | Valuation months and benchmarks not re-run |
| Realized P&L and total return | No | Unrealized only | — | Not defined. Do not show a new return number |
| Research / health | Partial | Scoring and Clear Dividend Risk 1.2 | Not run this gate | Screener prompt is absent |
| Isolation | Partial | `user_id` on portfolio rows | Postgres integration not run | Not verified against two live accounts |
| Support and legal | Partial | `SECURITY.md`, `PRIVACY.md`, `TERMS.md`, `SUPPORT.md`, `LICENSE` | — | `[OWNER ACTION REQUIRED: …]` still in the files |
| Excluded: IBKR sync, trading, payments, public sharing | Out of scope | `docs/releases/BETA_SCOPE.md` | — | Still absent, which is correct |

## B. Validation results

| Gate | Result | Evidence |
|---|---|---|
| `git diff --check` | PASS | Exit 0 on the dirty tree, 2026-11-12 |
| Focused replace, cash, and month tests | PASS | 13 passed, then 2 apply-import tests in 260.40s, Python 3.15.2 |
| Broker import, clear, cash, month file | PASS | 49 passed in 2126.76s, started 2026-11-12T09:31:06Z. The tree changed during that process |
| Killed replace, missing quarter, unpriced weight | PASS | 4 passed after those edits, Python 3.15.2 |
| `pytest -m "not integration"` | FAIL | Finished 2026-11-12T11:00:20Z, exit 1, 2568.56s, Python 3.15.2. 11 failed: 8 in `test_command_center_apptest.py` and `test_command_center_interactions.py`, 2 in `test_market_library_migration.py` (`chromadb` missing), 1 in `test_yield_channel_history.py` (`6 == 5`) |
| `pre-commit run --all-files` | NOT RUN | Not started during the unit suite |
| Python 3.11 and 3.12 CI | NOT RUN | No 3.11/3.12 environment used |
| Postgres 16 migrate and `pytest -m integration` | BLOCKED | No `psql` or `docker` on PATH. 13 integration tests collected, 0 run |
| Journeys A–D | NOT RUN | No staging session, no second account, no browser pass |
| Backup and restore of Postgres | NOT RUN | Beta success criteria ask for a tested backup. Only the replace recovery file was tested |
| Auth, secrets, HTTPS, performance, dependency review | NOT RUN | — |
| 2022–2026 cent reconciliation | BLOCKED | No anonymized broker fixture |

## C. Unresolved issues

### P0

- The candidate is not a commit. Publishing `930fef8` would omit the uncommitted financial fixes. There is nothing to tag.
- Owner contacts, public URL, hosting, governing law, and the copyright name are still placeholders. `docs/releases/v0.1.0-beta.1.md` says not to publish until those are resolved.
- No Postgres backup was restored, and the integration tests did not run. The beta success criteria require a tested backup.
- Broker reconciliation for 2022–2026 cannot be reproduced. The acceptance bar of zero unexplained differences is not met.
- The unit suite failed: 11 tests, exit 1, Python 3.15.2, 2026-11-12T11:00:20Z. Eight are guest command-center flows. Two need `chromadb`, which does not install on 3.15. One history-year estimate returned 6 instead of 5.
- Sign-in, allowlist, and two-account isolation were not exercised.

### P1

- Primary journeys were not clicked through. Disabled PDF, estimated-income labels, and import errors were not checked in a browser.
- Realized gain and total return are unspecified.
- A month with no market price can still be stored as a silent zero in the valuation path (FIN-005). That suite was not run here.

### P2

- Screener, yield filter, materials examples, allocation targets, portfolio-aware discovery, local models, and the investor pitch stay deferred. They must not be described as available.
- `DEPLOY-GCP.md` still describes Chroma and SQLite as the live disk layout.
- The README-only remote branch `origin/copilot/update-readme-organize-changes` should not be merged over the current README.

## D. Release recommendation

**NO-GO:** A critical defect, mandatory test failure, unverified release dependency or required owner approval remains unresolved.

Mandatory gates that did not pass: the full unit suite, Postgres integration, Python 3.11/3.12 CI, backup and restore, owner approval of the legal placeholders, and the broker reconciliation. The in-app replace recovery and the focused cash tests passed. They do not clear those gates.

Do not tag, deploy, or publish. The draft commands in `docs/releases/v0.1.0-beta.1.md` stay unused until the owner approves a later candidate.

## E. Final deliverables

1. Requirement matrix: section A of this file, and `docs/releases/BETA_VALIDATION.md`.
2. Financial reconciliation: blocked. Owner constants are labeled owner-only. No anonymized 2022–2026 statement was available. Focused receipt, replace, and missing-quarter tests passed on Python 3.15.2.
3. Integration and regression: 49-test import run passed on an earlier moment of this tree. The unit suite then failed with 11 tests. 13 Postgres tests were not run.
4. UI/UAT: not run.
5. Security and isolation: code is per `user_id`. Live two-account check was not run. Secrets were not audited beyond the existing gitignore of `.env`.
6. Backup, restore, rollback: replace failure and killed-process recovery tests passed. No database backup was restored.
7. Post-beta backlog: Band F and the screener rows in `docs/implementation-roadmap.md`.
8. Recommendation: **NO-GO**.
