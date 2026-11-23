# DividendScope implementation roadmap

Authoritative register for June–November 2026 requirements and Integration Plan v3.0.

Phase 0 inventory, then the Band A cash and replace fixes below. Later bands are not implemented.

Do not delete a row. If a decision replaces an older one, keep the old ID and set **Change** to `Superseded by <ID>`.

Status values: **Implemented**, **Partial**, **Missing**, **Broken**, **Deferred**. Payments, trading, and public sharing of real portfolios stay **Deferred** and out of the current beta (`docs/releases/BETA_SCOPE.md`).

**Verification** is Pass / Fail / Blocked / Not run. It means the acceptance check was executed in this audit. Reading a test file is not a pass. Every row below is **Not run**: this machine has Python 3.9.6 only, no project virtualenv, and no `pytest`. The suite in the tree has 810 `test_*` functions. CI is `.github/workflows/lint.yml` and `.github/workflows/tests.yml` (unit on 3.11 and 3.12, integration against Postgres 16). GitHub pull-request listing was not available (`gh` returned Forbidden). Merged PR numbers below come from local `git log`.

## Baseline

| Item | Result |
|---|---|
| Date | 2026-11-12 |
| Branch | `main` at `930fef8` ("What is real"), tracking `origin/main` |
| Working tree | No staged or unstaged tracked changes at audit start. No stash. No local branch other than `main` |
| vs remote | `HEAD` equals `origin/main`. Nothing to pull or push |
| Commits since 2026-06-01 | 214. First that day: `b0041fa` |
| Unmerged remote branch | `origin/copilot/update-readme-organize-changes` (`dc6fa52`, `ca7ab45`) changes only `README.md`. It is an older README rewrite, not unpublished feature code. Do not merge it over the current README |
| Other `origin/copilot/*` and `origin/feature/*` branches | Already contained in `main` (merged history includes PRs #2–#18) |
| Migrations | `migrations/001`–`012` |
| This file | Was ignored by `.gitignore` rule `docs/*`. Exception `!docs/implementation-roadmap.md` added so the register can be tracked. `docs/releases/` and `docs/product/` were already exceptions |

Tracked product docs that exist: `README.md`, `CHANGELOG.md`, `AGENTS.md`, `.cursor/rules/*.mdc`, `docs/releases/BETA_SCOPE.md`, `docs/releases/v0.1.0-beta.1.md` (draft, owner placeholders), `docs/product/dividendscope_launch_pitch_demo.html`, `DEPLOY-GCP.md` (still describes Chroma and SQLite as the live disk layout; runtime rule is PostgreSQL when `DATABASE_URL` is set).

## Dependency map

One owner per box. Later features must call that owner.

```
IBKR CSV
  → services/ibkr_activity_parser.py
  → validate_statement / preview_import
  → services/portfolio_broker_import_service.apply_import
       MERGE: sync lots, drop fully sold symbols, upsert receipts, merge deposits
       REPLACE: services/portfolio_clear_service.restoring_portfolio_on_failure
                snapshot, clear, insert; restore the snapshot if the write raises
  → services/portfolio_context.py
       holdings, purchase journal, dividend_receipts, net_dividends, deposits
  → services/portfolio_dividend_sync_service.py
  → services/portfolio_month_dividends.py
  → services/portfolio_dividend_cash.py
  → services/portfolio_dividend_quarters.py
  → UI: ui/portfolio_manage_panel.py, ui/portfolio_details_view.py, ui/command_center_home.py

Market providers (Yahoo, then SEC EDGAR, then Stooq)
  → data_ingestion/providers/composite.py
  → shared market library (services/shared_market_db.py)
  → research: services/scoring.py, services/clear_dividend_risk.py (methodology 1.2)
  → services/portfolio_allocation_service.py
  → UI research and holdings

Separate valuation path (do not treat as fundamental precedence)
  → services/portfolio_monthly_valuation.py (Stooq, then Yahoo)
  → services/portfolio_benchmark_service.py
  → services/fx_rate_service.py

Auth
  → auth/user_context.py
  → portfolio rows scoped by user_id
  → services/portfolio_ui_cache.py
  → demo: services/guest_playground.py (isolated from the signed-in book)
```

Shared calculations with more than one writer:

| Figure | Writers today | Consumers |
|---|---|---|
| Posted dividend gross / withholding / net | `build_canonical_dividends` + `upsert_broker_receipt`; library sync adds computed receipts only when no broker month exists | Month card, income records, quarterly script, holding `dividends_paid` |
| Month net after tax | `_resolve_month_gross_and_net` and `build_merged_dividend_income_records` use stored receipt net. Sync writes that same broker net. `net_received_through` (10%) runs only when the month has no stored net | Dividend income UI, heatmap |
| Month received gross | Receipt query filtered to open symbols. Receipt gross wins when receipt rows exist. Library gross is used only for months with no receipts | "Paid so far", current-month card |
| Position market value | Detail rows (`current_value`, else acquisition in allocation) | Summary, sector weights |
| Open vs closed book | `drop_holding` on merge; `delete_holding` on user delete; `clear_user_portfolio` on replace | Positions table, month filter, receipt history |

## Source-of-truth conflicts

These block Phase 1 implementation until the owner is explicit. They are the gate for this audit.

1. **REPLACE deletes before it writes.** Resolved locally by IMP-012: a snapshot is restored if the write raises. The success path still replaces the book. Merge does not clear.
2. **Two cash scopes are both intentional.** Commit `8d01016` limits "paid so far" and the current month to symbols you still hold, and limits month-over-month comparison to that same set. `test_import_stores_dividends_for_closed_positions` and `test_merge_drops_fully_sold_holding_keeps_history` keep closed-position receipts in the store. `quarterly_gross_from_receipt_store` includes sold tickers. Unifying these without a new decision would delete a reviewed behavior.
3. **Broker net is stored, then estimated again.** Resolved locally by FIN-010 and FIN-011 for the month resolver and merged income records. A flat 10% remains only when the month has no stored receipt net. `dividend_tax_rate()` is still 0.10 for that estimate.
4. **Overlap rule is "larger or combined," not event identity alone.** Manage-panel help text: overlapping deposit months use the larger or combined total. That matches `test_merge_accumulates_complementary_deposits_same_month` and `test_merge_multiple_statements_same_year_without_double_count`. It is a product rule. It is not the same rule as "sum of source events."
5. **2022–2026 reference totals have no source file.** The constants remain, marked `IBKR_REFERENCE_OWNER_ONLY`. The dividend page does not claim a match against them. The original statements are not in the workspace. A 2024-style synthetic fixture exists. A 2022 activity CSV does not.
6. **Risk methodology is 1.2.** `METHODOLOGY_VERSION = "1.2"` in `services/clear_dividend_risk.py`. README matches. Commit `b0c8795` introduced alerts as methodology 1.0; `f07b370` tightened High. That 1.0 label is superseded. Screening work must not change these thresholds.
7. **Screener prompt is absent.** No prompt file and no screener module. `ScoringService` is a different feature. Do not invent the prompt.
8. **Deploy doc vs runtime.** `DEPLOY-GCP.md` still tells operators that Chroma and SQLite survive on the VM disk. `AGENTS.md` forbids those runtimes when `DATABASE_URL` is set.

## Integration matrix

**Change** is a commit when one commit is the behavior's owner. Blank means the behavior accumulated across the June–November history. Verification for every row: **Not run**.

### ENG

| ID | Feature | Source | Status | Code | Dependencies | Tests | Acceptance | Verification | Change |
|---|---|---|---|---|---|---|---|---|---|
| ENG-001 | Ruff and Ruff-format gate commits and CI | Plan v3 §4 | Implemented | `.pre-commit-config.yaml`, `.github/workflows/lint.yml` | All Python | CI lint | Hook remains the only formatter | Not run | |
| ENG-002 | mypy on changed modules; blanket suppressions are not strictness | Plan v3 §4.3 | Partial | pre-commit `--strict`; `pyproject.toml` disables many codes for `services.*`, `ui.*`, `tests.*` | Financial modules | pre-commit | Band A files add no new blanket ignore | Not run | |
| ENG-003 | Vulture reports unused code | Plan v3 §4 | Implemented | pre-commit vulture | Call-graph before deletes | pre-commit | Hook stays | Not run | |
| ENG-004 | Unit tests use SQLite; integration tests use Postgres | Plan v3 §4.2 | Implemented | `tests/conftest.py`, `tests.mdc` | Every store | `pytest -m "not integration"`; `pytest -m integration` | Unit job does not set `DATABASE_URL` | Not run | `90fb5cd` |
| ENG-005 | `AGENTS.md` plus scoped `.cursor/rules/` | Plan v3 §4.1 | Implemented | `AGENTS.md`, six rule files | Agents | — | No second agent-config tree | Not run | `4449455` |
| ENG-006 | One behavior path; diffs stay small | Plan v3 §6 | Implemented | `agent-discipline.mdc` | Every change | review | Task names files before editing | Not run | |
| ENG-007 | Services log through `utils.logging_config` | Plan v3 §4 | Partial | `utils/logging_config.py` | Services | — | New service code does not use `print` | Not run | |
| ENG-008 | Schema changes are migrations plus SQLite `_ensure_schema` | Plan v3 §4.2 | Implemented | `migrations/001`–`012` | Stores | `tests/test_postgres_storage.py` | No column without both paths | Not run | `0196e07` for `011` |
| ENG-009 | DB dates use `db.parsing` | Code, June 1 | Implemented | `db/parsing.py` | All stores | `tests/test_db_parsing.py` | No new `date.fromisoformat` on driver row values | Not run | `bb7f3bc` |
| ENG-010 | Portfolio rebuilds run as background jobs | Plan v3 §4.1 | Implemented | `services/portfolio_refresh.py`, `services/deferred_startup.py` | UI | `tests/test_portfolio_refresh.py` | Render paths call `schedule_portfolio_reload`; IBKR apply calls `reload_portfolio_after_data_import` | Not run | |
| ENG-011 | Automatic extra jobs stay off unless the price-sync exception applies | Code | Implemented | `services/background_task_prefs.py` | Startup | `tests/test_background_task_prefs.py` | New automatic jobs check the preference | Not run | |
| ENG-012 | PostgreSQL is production storage when `DATABASE_URL` is set | AGENTS | Implemented | `db/connection.py`, `services/shared_market_db.py` | All persistence | `tests/test_shared_market_db.py` | No new runtime Chroma or per-user SQLite writes | Not run | `e754417` |
| ENG-013 | Caches follow the portfolio fingerprint | Plan v3 §0.3 | Partial | `services/portfolio_ui_cache.py` | Month cash, risk summary | `tests/test_portfolio_ui_cache.py` | Receipt edits invalidate displayed totals | Not run | `b0041fa` |

### IMP

| ID | Feature | Source | Status | Code | Dependencies | Tests | Acceptance | Verification | Change |
|---|---|---|---|---|---|---|---|---|---|
| IMP-001 | Historical IBKR Activity Statement CSVs parse | Plan v3 §1.1 | Partial | `services/ibkr_activity_parser.py` | Import service, UI preview | `tests/test_ibkr_activity_parser.py` | Each supported layout has a fixture | Not run | |
| IMP-002 | 2022 and 2024 format cases | Plan v3 §1.1 | Partial | Fixture `tests/fixtures/ibkr_activity_2024_style.csv`. 2022 file absent | FIN-001 | `test_parse_2024_style_export` | 2024 fixture stays. 2022 file is added only when the owner supplies it | Not run | |
| IMP-003 | Preview and validation before apply | Plan v3 §1.1 | Implemented | `preview_import`, `validate_statement` | Manage panel | `test_preview_sample` | Blocking errors do not write | Not run | |
| IMP-004 | Stable dividend identity | Plan v3 §1.1 item 8 | Implemented | `data_ingestion/dividend_transaction.py` | Receipt store, migrations `010`–`012` | `tests/test_dividend_receipt_dedup.py` | Same economic row, same key, regardless of filename | Not run | `0196e07` |
| IMP-005 | Same file imported twice does not change totals | Plan v3 §1.1 | Implemented | `apply_import` MERGE | Receipts, journal, deposits | `test_merge_same_file_twice_is_idempotent` | Second apply does not double shares or cash | Not run | |
| IMP-006 | Corrected events update one row | Plan v3 §1.1 item 8 | Partial | `upsert_broker_receipt` outcomes added/updated/duplicate | IMP-004 | Dedup tests cover same key. A corrected amount with a new identity is not a dedicated case | One symbol's amount changes; other symbols do not | Not run | |
| IMP-007 | Sold holdings leave the open book and keep journal and receipts | Plan v3 §1.1 item 5 | Implemented | `drop_holding` on MERGE | Month display scope FIN-016 | `test_merge_drops_fully_sold_holding_keeps_history`, `test_import_stores_dividends_for_closed_positions` | Open table omits the symbol; receipts remain | Not run | |
| IMP-008 | Read-only IBKR account sync | Beta exclusion, Plan v3 deferred | Deferred | — | IMP-001–IMP-012 | — | Not in this beta | Not run | |
| IMP-009 | Cross-year gaps are warnings, and older-dated rows are kept | Code | Implemented | `statement_history_coverage_gaps` | Parser | Parser tests | Info warning only | Not run | |
| IMP-010 | Non-USD stock rows and missing FX are explicit | Plan v3 §1.1 item 11 | Partial | Forex asset category is skipped. USD stock filter. `fx_rates` stored for deposits | FIN-008 | `test_parse_2024_style_export` | A non-USD stock row is imported with currency or rejected with an issue | Not run | |
| IMP-011 | Overlapping periods reconcile deterministically | Plan v3 §1.1 item 3 | Partial | MERGE deposit merge; help text in Manage panel | IMP-005 | `test_merge_second_year_keeps_first_year_trades`, `test_merge_multiple_statements_same_year_without_double_count`, `test_merge_accumulates_complementary_deposits_same_month` | Documented rule: matching identities update; complementary same-month deposits combine; larger month total wins where that helper says so | Not run | |
| IMP-012 | REPLACE either rolls back or is not offered as safe | Plan v3 §1.1 | Implemented | `restoring_portfolio_on_failure` snapshots holdings, journal, receipts, net dividends, and deposits, then `apply_import` restores that snapshot if the write raises. Session cache clears only after success | All portfolio stores | `test_replace_failure_after_clear_restores_previous_portfolio` | Injected failure after clear leaves the previous book | Pass | local, uncommitted |
| IMP-013 | Unsupported and malformed rows are visible | Plan v3 §1.1 items 10–12 | Partial | `validate_statement`, rejected dividend count, import issues | UI preview | Parser and import tests | User sees issues. Partial apply does not claim success after a crash | Not run | |
| IMP-014 | Corporate actions and special distributions | Plan v3 §1.1 item 9 | Partial | 2024 fixture expects no Corporate Actions section. Payment-in-lieu and reversals are parsed. Reversals are skipped on apply (`test_import_skips_dividend_reversals`) | Canonical dividends | `test_parse_2024_style_export`, `test_import_skips_dividend_reversals` | Each special type is stored, excluded with a reason, or reported unseen | Not run | |

### FIN

| ID | Feature | Source | Status | Code | Dependencies | Tests | Acceptance | Verification | Change |
|---|---|---|---|---|---|---|---|---|---|
| FIN-001 | 2022–2026 broker discrepancy is a receipt-level fixture | Plan v3 §1.2 | Partial | Constants stay in `services/portfolio_dividend_quarters.py` and are marked `IBKR_REFERENCE_OWNER_ONLY`. The dividend page no longer claims they match a statement. Offline script `scripts/validate_dividend_quarters.py` can still read them | IMP-002 | `tests/test_portfolio_dividend_quarters.py` | Sanitized events sum to the reference, or the constants are marked owner-only and leave product code | Pass for owner-only | `9e0b87f`, local |
| FIN-002 | Gross, withholding, and net are separate stored fields | Plan v3 §1.2 | Implemented | `dividend_receipts` columns, migration `011` | UI copy | Receipt and import tests | A posted row keeps all three | Not run | `0196e07` |
| FIN-003 | Received and projected income stay distinct | Plan v3 §1.2 | Partial | `services/dividend_terminology.py`. Display helpers still mix sources (FIN-010, FIN-011) | Month card, income page | Guest and cash tests | Received totals move only when broker rows move | Not run | `e385cb7` |
| FIN-004 | Quarterly, annual, and partial-year comparisons | Plan v3 §1.2 | Partial | `compare_quarterly_gross`, `compare_annual_net`, `PARTIAL_REFERENCE_QUARTERS` | FIN-001 | Quarter tests | Completed years match within one cent. The open year is labeled partial | Not run | |
| FIN-005 | Historical portfolio value, including months with no purchase | Plan v3 §1.3 | Partial | `sync_monthly_portfolio_timeline`, `services/portfolio_monthly_valuation.py` | Journal, FX, prices | `tests/test_portfolio_monthly_valuation.py` | A month with no price is incomplete, not a silent zero | Not run | `c1933f9`, `b91f275` |
| FIN-006 | Deposits, withdrawals, trades, corporate actions in cash flow | Plan v3 §1.3 | Partial | Deposits and trades import. No single cash-flow statement | IMP-014 | Deposit parser tests | Each class is included or reported unseen | Not run | |
| FIN-007 | Cost basis, realized and unrealized gain, total return | Plan v3 §1.3 | Partial | Unrealized in `services/portfolio_holdings_summary.py`. No realized or total-return definition | FIN-008 | `tests/test_portfolio_holdings_summary.py` | Unrealized stays value minus cost. Realized and total return are specified before a new number is shown | Not run | |
| FIN-008 | Base currency and transaction currency both kept | Plan v3 §1.2 | Partial | Statement base currency, deposit EUR and USD, `services/fx_rate_service.py` | IMP-010, benchmarks | Import tests around EUR samples | Original amount, currency, and rate used are recoverable | Not run | `44f45bd` |
| FIN-009 | Benchmark method is stated | Plan v3 §1.3 | Partial | `services/portfolio_benchmark_service.py` hypothetical same-deposit index/ETF shares, euro display | FIN-007 | `tests/test_benchmark_store.py` | Caption states proxies, deposit rule, and currency | Not run | `b35ddc7` |
| FIN-010 | Real withholding wins over the flat 10% rate | Plan v3 §1.2 pass criteria | Implemented | Receipt net is used by `_resolve_month_gross_and_net` and `build_merged_dividend_income_records`. `dividend_tax_rate()` remains the estimate only when a month has no stored net | FIN-002 | `test_merged_records_keep_broker_withholding`, `test_resolve_month_dividend_cash_keeps_receipts_when_library_is_higher` | Stored net $85 on $100 gross stays $85. 10% appears only as an estimate | Pass | local, uncommitted |
| FIN-011 | Posted receipts are the received gross | Plan v3 §1.2 | Implemented | `_resolve_month_gross_and_net` keeps receipt gross whenever receipt rows exist. Library gross is used only for months with no receipts, and that source is `computed` | Month card | `test_resolve_month_dividend_cash_keeps_receipts_when_library_is_higher` | Receipts $50 and library $100 display received $50 | Pass | local, uncommitted |
| FIN-012 | Historical received totals include sold symbols | Plan v3 §1.3 | Partial | Store keeps them (IMP-007). Quarter helper includes them. Month card does not (FIN-016) | FIN-016 | Closed-position import tests | Any view that claims account history includes those receipts | Not run | |
| FIN-013 | Missing data is distinct from a reported zero | Plan v3 §1.3 pass criteria | Partial | A quarter absent from receipts is status `missing`. 2026 Q4 is no longer a stored `0.00`. The month card shows "—" when there are no payments. A stored `0.00` still matches as a reported zero. Other `COALESCE(SUM, 0)` readers remain | FIN-004, PORT-002 | `test_missing_quarter_is_not_reported_as_zero`, `test_reported_zero_quarter_still_matches` | Empty and unknown are not shown as zero | Pass for quarter compare and the month card | local |
| FIN-014 | Cash totals use payment date | Plan v3 §1.2 | Implemented | `services/dividend_payment_dates.py`, quarter helper | Receipts | `tests/test_dividend_payment_dates.py` | Pay date and ex-date are labeled | Not run | `9e0b87f` |
| FIN-015 | User can see reference, computed, and delta | Plan v3 §1.2 | Partial | Comparator exists. A dividend-page reconciliation table was not confirmed | FIN-001 | Quarter tests | Completed year shows all three | Not run | |
| FIN-016 | "Paid so far" and current-month payers are open holdings only | Commit `8d01016` | Implemented | `current_month_paid_dividends` passes open symbols into the receipt sum. The month card caption states that limit. `scope` is `open_holdings` | IMP-007, FIN-012 | `test_current_month_card_uses_open_holdings_only`, `test_gross_paid_in_calendar_month_filters_to_open_symbols` | The month card states the open-holding scope. Account-history views keep FIN-012 | Pass | `8d01016`, local caption |

### DATA

| ID | Feature | Source | Status | Code | Dependencies | Tests | Acceptance | Verification | Change |
|---|---|---|---|---|---|---|---|---|---|
| DATA-001 | Fundamentals can show filing source and date | Plan v3 §2.1 | Partial | SEC provider, `services/analysis_evidence.py` | Research UI | `tests/test_analysis_evidence.py` | A shown fundamental has provider and as-of, or an insufficient-data flag | Not run | |
| DATA-002 | Yahoo, SEC EDGAR, and Stooq remain the sources | Plan v3 §2.1 | Implemented | `default_providers()` | Enricher | `tests/test_stock_providers.py` | No new vendor without a new ID | Not run | `07e78ae` |
| DATA-003 | Provenance, freshness, and currency are visible | Plan v3 §2.1 | Partial | `render_data_provenance`, 45-minute stale threshold | Prices, FX | Guest provenance tests | Price-derived numbers show source and as-of | Not run | `14d888b` |
| DATA-004 | Later providers fill gaps and do not overwrite scalars | Plan v3 §2.1 | Implemented | `MultiSourceEnricher` | DATA-002 | Provider tests | A populated yield stays | Not run | |
| DATA-005 | Research history documents split handling | Plan v3 §2.1 | Partial | `_looks_like_split_adjustment` inside risk | Clear Dividend Risk | `tests/test_clear_dividend_risk.py` | Portfolio cash still follows broker events | Not run | |
| DATA-006 | Missing market data is reported | Plan v3 §2.1 | Partial | Dividend data warnings; valuation may backfill the other vendor | FIN-005 | Cash and valuation tests | Warning names the symbol and field | Not run | |
| DATA-007 | Library ingestion is shared and batched | Plan v3 §4.1 | Implemented | `ingest_data.py`, `services/shared_market_db.py` | Research, portfolio | `tests/test_ingest_data_cli.py` | No per-symbol query loop added on the render path | Not run | |
| DATA-008 | Fundamental precedence stays Yahoo → EDGAR → Stooq | Plan v3 §2.1 | Implemented | `composite.py` | DATA-002 | Provider tests | A precedence change is a new ID | Not run | |
| DATA-009 | Valuation price history may prefer Stooq | Code | Implemented | `portfolio_monthly_valuation.py` | FIN-005 | `tests/test_portfolio_monthly_valuation.py` | Valuation source is labeled and does not change DATA-008 | Not run | |

### RES

The original screener prompt is not in the workspace. These rows preserve the requirement. They do not reconstruct the prompt.

| ID | Feature | Source | Status | Code | Dependencies | Tests | Acceptance | Verification | Change |
|---|---|---|---|---|---|---|---|---|---|
| RES-001 | Preserve the historical screener prompt and output | Plan v3 §2.3 | Missing | No prompt file. `services/scoring.py` is a score, not that screener | — | — | Recover the prompt or record a formal replacement | Not run | |
| RES-002 | Version condensed prompts without dropping rules | Plan v3 §2.3 | Missing | FAQ strings in `services/chatbot_service.py` | RES-001 | — | Version file exists only after RES-001 | Not run | |
| RES-003 | Yield, 3/5/10-year dividend CAGR, streak, consistency | Plan v3 §2.3 | Partial | Score uses streak, yield, growth. Document fields include 5Y and 10Y CAGR | DATA-004 | `tests/test_scoring_service.py`, `tests/test_dividend_streak.py` | 3Y is calculated or marked unavailable | Not run | |
| RES-004 | Earnings, FCF, debt, valuation | Plan v3 §2.3 | Partial | Risk signals and score payout terms | DATA-001 | Risk tests | Absent ratios are omitted | Not run | |
| RES-005 | REIT, BDC, and bank coverage use the right metric | Plan v3 §2.1–2.3 | Partial | `SecurityType` REIT, BANK_INSURER, ETF_FUND. REIT requires FFO/AFFO. No BDC | RES-004 | `tests/test_clear_dividend_risk.py` | BDC is classified or marked insufficient. REIT does not rank on GAAP payout alone | Not run | |
| RES-006 | Sources and reporting dates on research claims | Plan v3 §2.3 | Partial | `analysis_evidence` | DATA-003 | `tests/test_analysis_evidence.py` | Each claim has a source or an insufficient-data flag | Not run | |
| RES-007 | Configurable filters, including yield ≤ 3% | Plan v3 §2.3 | Missing | `config.py` yield bands feed the score only | RES-001 | — | Max yield 3% excludes higher yields | Not run | |
| RES-008 | Dividend-growth-over-yield ranking | Plan v3 §2.3 | Missing | Score mixes several weights | RES-003 | — | Pure function, fixed inputs, stable order | Not run | |
| RES-009 | Materials-sector top 2 and top 5 examples | Plan v3 §2.3 | Missing | Sector alias in `data_ingestion/sp500_universe.py` | RES-008 | — | Example uses a fixture universe and records the filter | Not run | |
| RES-010 | Rank, risk flags, and missing data are explainable | Plan v3 §2.3 | Implemented | Score breakdown; risk signal codes | RES-005 | Scoring and risk tests | Component points are visible | Not run | `42a7d36` |
| RES-011 | Comparison table stays on the decision columns | Plan v3 §2.3 | Missing | Holdings tables are wider | RES-001 | — | Extra detail stays on the company page | Not run | |
| RES-012 | Screening cannot write portfolio holdings | Plan v3 §2.3 pass criteria | Implemented | Research loaders do not call holding upserts | Portfolio store | Needs a guard test if a screener is added | Screener output is read-only | Not run | |

### PORT

| ID | Feature | Source | Status | Code | Dependencies | Tests | Acceptance | Verification | Change |
|---|---|---|---|---|---|---|---|---|---|
| PORT-001 | Open positions and quantities | Plan v3 §2.2 | Implemented | `services/portfolio_open_holdings.py` | IMP-007 | `tests/test_portfolio_open_holdings.py` | Sold symbols are absent from the open book | Not run | |
| PORT-002 | One market-value definition for every weight | Plan v3 §2.2 | Implemented | Sector and market-cap weights use `current_value` only. `unpriced_tickers` is listed under the allocation caption | FIN-008, DATA-003 | `test_unpriced_holding_is_excluded_from_sector_weights` | Unpriced holdings are listed and excluded from the denominator | Pass | local |
| PORT-003 | Holding and sector market-value weights | Plan v3 §2.2 | Partial | `sector_allocation`, market-cap buckets, `ui/portfolio_details_view.py` | PORT-002 | — | Sector weights sum to the eligible denominator | Not run | |
| PORT-004 | Dividend-income share by holding and sector | Plan v3 §2.2 | Partial | Income concentration alerts in `clear_dividend_risk.py`, separate from market-value weights | FIN-003, FIN-016 | Risk tests | Label says received or estimated, and names the scope (open book vs account history) | Not run | `ebf6fe8` |
| PORT-005 | Missing sectors against a chosen universe | Plan v3 §2.2 | Missing | Allocation lists sectors that have positions | PORT-003 | — | Absent sectors appear only when a universe is selected | Not run | |
| PORT-006 | User target weights and gaps | Plan v3 §2.2 | Missing | No target store | PORT-003 | — | No "underweight" label without a saved target | Not run | |
| PORT-007 | Concentration and overlap | Plan v3 §2.2 | Partial | Company and sector income alerts, yield-gated | PORT-004 | `tests/test_clear_dividend_risk.py` | Existing yield gate stays until a new ID changes it | Not run | |
| PORT-008 | Candidates aware of current weights | Plan v3 §2.4 | Missing | S&P picker and peers are not weight-aware | RES-008, PORT-004 | — | Shortlist shows the sector's current weight | Not run | |
| PORT-009 | Cash-contribution scenarios before any sell case | Plan v3 §2.4 | Deferred | No simulator | PORT-006 | — | A scenario does not propose sells | Not run | |
| PORT-010 | Scenario impact on yield, growth, and risk | Plan v3 §2.4 | Deferred | Benchmark page is FIN-009 only | PORT-009 | — | Uses the same valuation function as PORT-002 | Not run | |
| PORT-011 | Educational analysis, no trade instructions | Beta, Plan v3 §2.4 | Implemented | Disclaimers, chatbot, terms | UI copy | `tests/test_chatbot_service.py` | No order ticket | Not run | |

### AI

| ID | Feature | Source | Status | Code | Dependencies | Tests | Acceptance | Verification | Change |
|---|---|---|---|---|---|---|---|---|---|
| AI-001 | Existing assistant remains | Plan v3 §3.1 | Implemented | `services/chatbot_service.py`, `ui/chatbot_widget.py` | — | `tests/test_chatbot_service.py` | FAQ answers with no token | Not run | `c09defd` |
| AI-002 | Optional hosted model; local model only if a gap requires it | Plan v3 §3.1 | Partial | Hugging Face when `HUGGINGFACE_API_KEY` or `HF_TOKEN` is set. No local runtime | AI-001 | Chatbot tests | App works with the model disabled. Local runtime stays deferred | Not run | `a27ee84` |
| AI-003 | Provider-independent evidence packet | Plan v3 §3.1 | Deferred | HF conversational payload only | RES-010 | — | Adapters share one evidence object | Not run | |
| AI-004 | Claims stay inside computed results | Plan v3 §3.1 | Partial | FAQ is authored. HF text is returned as generated | AI-001 | Chatbot tests | Model text cannot add a dividend amount | Not run | |
| AI-005 | The model does not author financial totals | Plan v3 §3.1 | Partial | Same split as AI-004 | FIN-010 | — | Totals come from FIN owners | Not run | |
| AI-006 | Dated cost, latency, and privacy comparison | Plan v3 §3.1 | Deferred | Not in repo | AI-002 | — | Documentation only | Not run | |
| AI-007 | Product works with AI disabled | Plan v3 §3.1 | Implemented | FAQ and fallback; `DIVIDENDSCOPE_CHATBOT_ENABLED` | — | Chatbot tests | Disabled flag leaves portfolio usable | Not run | |
| AI-008 | Holdings table is not sent to the hosted model | Plan v3 §3.1 | Partial | `reply_via_huggingface` sends conversation text. Server-side FAQ can mention session tickers. Typed chat can include holdings | SEC-002 | Chatbot tests | Default payload has no `portfolio_details_rows` | Not run | |

### UX

| ID | Feature | Source | Status | Code | Dependencies | Tests | Acceptance | Verification | Change |
|---|---|---|---|---|---|---|---|---|---|
| UX-001 | Streamlit remains the UI | Plan v3 §3.2 | Implemented | `app.py`, `ui/` | — | — | No framework migration | Not run | |
| UX-002 | Navigation and primary buttons do what they say | Plan v3 §3.2 | Partial | Sidebar, manage, onboarding. PDF button is `disabled=True` when `reportlab` is missing (`ui/views.py`) | — | `tests/test_command_center_routing.py`, `tests/test_home_interactions.py` | Disabled PDF is labeled unavailable, or the download works | Not run | `474bda1` |
| UX-003 | Historical dead controls | Commit `474bda1` | Partial | Import route, help links, home chips fixed in that commit. No separate defect list | UX-002 | Command-center interaction tests | Checklist stored under this ID after a UI pass | Not run | `474bda1` |
| UX-004 | Visual consistency inside the design system | Plan v3 §3.2 | Partial | `ui/design_system.py`, `ui/theme_mode.py` | UX-001 | `tests/test_design_system.py` | Style changes stay in the design system | Not run | |
| UX-005 | Public demo uses isolated sample data | Plan v3 §3.2 | Implemented | `services/guest_playground.py` | SEC-001 | `tests/test_guest_playground.py` | Demo reset does not write the signed-in book | Not run | `4a21bda` |
| UX-006 | Demo leads to sign-in and access request | Beta | Partial | `ui/auth_account_panel.py`, `ui/access_request_panel.py` | SEC-001 | `tests/test_command_center_routing.py`, `tests/test_access_requests.py` | Visitor can open demo, then request access | Not run | `28b78f0` |
| UX-007 | Loading, empty, and error states | Plan v3 §3.2 | Partial | Empty home, import issues, dividend warnings | FIN-013 | `tests/test_portfolio_empty_home.py` | Three distinct states | Not run | |
| UX-008 | Received vs estimated copy matches the calculation | Plan v3 §3.2 | Partial | Month card and dividend-income caption now follow FIN-010 / FIN-016. Other screens were not rewritten | FIN-010, FIN-011, FIN-016 | Guest tests still not re-run | Copy names broker net, estimated 10%, and open-holding scope on the dividend pages that were edited | Pass for those two captions | local, uncommitted |
| UX-009 | PDF, CSV, and JSON research export | Plan v3 §3.2 | Partial | `services/report_generator.py` | UX-002 | No report-generator test found | CSV and JSON stay. PDF state is honest | Not run | |
| UX-010 | Ten-step MVP walkthrough | Beta success criteria | Partial | Criteria in `BETA_SCOPE.md`. Not executed in this audit | UX-002, UX-006, UX-008 | AppTest modules exist | Results appended here after a run | Not run | |
| UX-011 | Demo must not present sample dividends as broker receipts | Plan v3 §3.2 | Partial | Guest playground builds illustrative cash, including a sample withholding | UX-005, FIN-003 | `tests/test_guest_playground.py` | Demo figures are labeled sample | Not run | |

MVP steps to execute later: open demo, explore sample holdings, open research, distinguish received from forecast, review risk and diversification, follow a CTA, sign in as an approved user, import a supported file, see source labels, open support and privacy.

### BIZ

Documentation only. Not an instruction to add payments.

| ID | Feature | Source | Status | Code | Dependencies | Tests | Acceptance | Verification | Change |
|---|---|---|---|---|---|---|---|---|---|
| BIZ-001 | Investor / demo presentation | Plan v3 deferred | Partial | `docs/product/dividendscope_launch_pitch_demo.html` exists. Not checked against verified IDs | UX-010 | — | Every claim maps to an Implemented row | Not run | |
| BIZ-002 | Presentation matches the product | Plan v3 §5 | Deferred | Draft beta notes | BIZ-001 | — | Claims cite this register | Not run | |
| BIZ-003 | Positioning write-up | Plan v3 deferred | Deferred | README feature table | — | — | — | Not run | |
| BIZ-004 | Competitor review | Plan v3 deferred | Deferred | — | — | — | Dated and sourced | Not run | |
| BIZ-005 | Target users | Beta | Partial | `BETA_SCOPE.md` "who it is for" | — | — | Matches invite-only beta | Not run | |
| BIZ-006 | Go-to-market notes | Plan v3 deferred | Deferred | — | BIZ-005 | — | — | Not run | |
| BIZ-007 | Monetization on paper only | Beta exclusion | Deferred | — | — | — | No billing code | Not run | |
| BIZ-008 | Beta feedback capture | Code | Partial | `services/beta_feedback.py`, migration `006` | UX-010 | `tests/test_beta_feedback.py` | Milestones point at beta success criteria | Not run | |
| BIZ-009 | No trading, payments, or public real portfolios | Beta | Deferred | Excluded list | — | — | Those features stay absent | Not run | |

### SEC

| ID | Feature | Source | Status | Code | Dependencies | Tests | Acceptance | Verification | Change |
|---|---|---|---|---|---|---|---|---|---|
| SEC-001 | Auth and per-user portfolio isolation | Plan v3 §5 | Implemented | `auth/user_context.py`, `user_id` on portfolio rows | Demo boundary | `tests/test_auth.py`, `tests/integration/test_postgres_live.py` | One user cannot read another's holdings | Not run | |
| SEC-002 | Privacy notice matches storage and outbound calls | Plan v3 §3.1 | Partial | `PRIVACY.md` draft; AI-008 | AI-008 | — | Notice names Google, Postgres, and optional HF | Not run | |
| SEC-003 | Broker access is file import only | Beta | Implemented | CSV path. IMP-008 deferred | IMP-012 | Import tests | No order or session-token client | Not run | |
| SEC-004 | Secrets out of git | Plan v3 §5 | Partial | `.env` gitignored | CI | — | No secret file tracked | Not run | |
| SEC-005 | Backup, restore, and rollback | Plan v3 §5 | Partial | IMP-012 restores a failed Full replace in-process and writes `*.replace-recovery.json` before the clear. The next portfolio open restores that file if the process was killed. A Postgres operator drill is still unwritten. `DEPLOY-GCP.md` is stale | ENG-012, IMP-012 | `test_killed_replace_restores_on_next_open` | Postgres restore drill written and executed | Pass for the killed-replace file | local |
| SEC-006 | Postgres migrations apply | Plan v3 §4.2 | Implemented | `python -m db --migrate` | ENG-008 | Integration tests | Fresh migrate and upgrade from the previous schema when a migration changes | Not run | |
| SEC-007 | Release stays unpublished until gates pass | Draft release | Partial | `docs/releases/v0.1.0-beta.1.md` says do not tag yet | SEC-005, SEC-008 | CI | No deploy without an explicit request | Not run | |
| SEC-008 | Legal and owner placeholders | Beta | Partial | `SECURITY.md`, `PRIVACY.md`, `TERMS.md`, `SUPPORT.md`, `LICENSE` | — | — | Owner fills `[OWNER ACTION REQUIRED: …]` before a public tag | Not run | |
| SEC-009 | Public issues and git fixtures stay sanitized | Beta | Implemented | Policy text. Fixtures under `tests/fixtures/` are small samples | IMP-002 | review | No full personal statement committed | Not run | |

## Dependency-ordered backlog

**Band A — stop data loss and pick one received-cash owner**

1. IMP-012 — REPLACE rollback, or remove the safe-looking Full replace action until the failure test exists.
2. FIN-011 — one received-gross function; library amount is an estimate.
3. FIN-010 — that function's net uses stored withholding.
4. FIN-016 and UX-008 — label the open-holding month card. Do not change FIN-012's store behavior in the same edit.
5. FIN-013 — empty vs zero on the totals those functions return.

**Band B — historical proof**

6. IMP-002 and FIN-001 — 2022 file only if provided; otherwise mark the constants owner-only.
7. FIN-004 and FIN-015 — cent-level annual and quarterly deltas from events.
8. IMP-006, IMP-011, IMP-014 — corrected events, overlap rule, special distributions.

**Band C — valuation and weights**

9. FIN-008, IMP-010, FIN-005, DATA-006.
10. PORT-002, PORT-003, PORT-004 using the Band A cash owner.
11. FIN-009 caption. FIN-007 definition before any new return number.

**Band D — research, after cash is stable**

12. RES-001, then RES-005, RES-007, RES-008, RES-009.
13. AI-004, AI-005, AI-008.
14. Re-run `tests/test_clear_dividend_risk.py` before and after any screening change. `METHODOLOGY_VERSION` stays 1.2 unless a new ID versions it.

**Band E — release**

15. UX-002, UX-003, UX-010, UX-011.
16. SEC-005, SEC-008.
17. ENG-002 on the files Band A touches.

**Band F — remain visible, do not start**

IMP-008, PORT-005, PORT-006, PORT-008, PORT-009, PORT-010, AI-002 local runtime, AI-003, AI-006, BIZ-002 through BIZ-007, BIZ-009.

## Three highest-priority integration tasks

Implement one at a time, after this inventory. Each task below is a validation gap in current code, not a new product surface.

### Task 1 — IMP-012 Make Full replace crash-safe

**Existing behavior.** "Full replace" in Manage portfolio calls `clear_user_portfolio` and then imports. Clear deletes holdings, journal, receipts, net dividends, and deposits. There is no transaction around clear plus write. `test_clear_user_portfolio_wipes_all_tables` covers the wipe. Nothing covers a failure after the wipe.

**Change to make.** Keep a single `apply_import` path. On REPLACE, either commit clear and write together so a failure restores the previous rows, or disable the Full replace control until that test exists. MERGE behavior stays as it is.

**Acceptance.** A test forces a failure after clear has started. The user's previous holdings, journal, receipts, and deposits are still present. Unchanged MERGE reimport tests still pass.

**Files to expect:** `services/portfolio_broker_import_service.py`, `services/portfolio_clear_service.py`, `tests/test_portfolio_broker_import.py`. UI copy only if the control is disabled.

### Task 2 — FIN-011 and FIN-010 One received-cash owner

**Existing behavior.** Receipts store gross, withholding, and net. Three helpers then disagree: sync prefers broker monthly net when the rollup has it; `build_merged_dividend_income_records` recomputes 10% from gross; `_resolve_month_gross_and_net` can display the larger library gross.

**Change to make.** One function returns received gross, received net, and an optional estimate. Month card and merged income records call it. Do not add a second calculator.

**Acceptance.** Receipts of $10 gross and $1.50 withholding display received net $8.50. A library figure of $25 is labeled estimated or omitted. A month with no withholding may show 10% only with an estimated label. `tests/test_clear_dividend_risk.py` is unchanged.

**Files to expect:** `services/portfolio_month_dividends.py`, `services/portfolio_dividend_cash.py`, `services/portfolio_dividend_sync_service.py`, their tests, and the 10% sentence in `ui/portfolio_details_view.py`.

### Task 3 — FIN-016 Lock the open-holding month scope

**Existing behavior.** Commit `8d01016` limits paid-so-far and the current month to current holdings. Closed-position receipts remain in the store.

**Change to make.** Add the missing assertion and a UI label. Do not add sold-symbol cash into the month card in this task. Account-history totals stay on the quarter/receipt path (FIN-012).

**Acceptance.** Open KO $10 plus a receipt for a symbol with no open holding $4: the month card shows $10 and says it is open holdings; the receipt store still returns both. Positions table still omits the closed symbol.

**Files to expect:** `services/portfolio_month_dividends.py`, `tests/test_portfolio_month_dividends.py`, the month-card caption in the dividend UI.

## Superseded decisions

| Old | Current owner | Change |
|---|---|---|
| Legacy Excel broker parser | IMP-001 `portfolio_broker_import_service.py` | Superseded; recorded in `AGENTS.md` |
| Runtime Chroma or per-user SQLite when `DATABASE_URL` is set | ENG-012 | Superseded |
| `delete_holding` for an IBKR merge of a sold symbol | IMP-007 `drop_holding` | Superseded |
| Blocking portfolio reload inside UI render | ENG-010 | Superseded |
| Top-level Dividend Kings and Single stock nav | UX-001 portfolio shell | Superseded in `ui/theme.py` |
| Clear Dividend Risk alert methodology 1.0 | RES-010 / risk `METHODOLOGY_VERSION` 1.2 | Superseded by `f07b370` and the 1.2 constant |
| `DEPLOY-GCP.md` live Chroma and SQLite layout | ENG-012 | Doc not yet edited |
| Treating "paid so far" as all-account history | FIN-016 for that card; FIN-012 for account history | Scope split from `8d01016`. Do not collapse without a new ID |

## Definition of done

A row becomes **Implemented** with Verification **Pass** only when:

- The named acceptance check was executed.
- Focused tests and the relevant suite passed.
- The figure is traceable to one owner in the dependency map.
- Existing behavior listed in this file still works.
- This row's Verification and Change cells are updated.

## Release validation (2026-11-12)

Decision: **NO-GO** for `v0.1.0-beta.1`. Evidence is in `docs/releases/BETA_VALIDATION.md` and `docs/releases/BETA_RELEASE_REPORT.md`.

HEAD remains `930fef8e7dfef4c765498cf7b8008f592e9375f9`. The financial fixes are uncommitted, so they are not the tagged candidate. No tag exists. Owner placeholders in the legal docs are still unresolved. The 2022 statement is still absent.

## Phase 0 gate

Inventory, conflicts, and the ordered backlog are in this file.

Band A items IMP-012, FIN-011, FIN-010, and FIN-016 are implemented locally and covered by focused tests on Python 3.15.2. They are not committed.

`test_apply_import_without_open_positions` and `test_merge_same_file_twice_is_idempotent` passed on Python 3.15.2 in 260 seconds. The wait is month-end price backfill. The replace-failure test patches that call.

Python 3.15 cannot install `chromadb` because `onnxruntime` and `pulsar-client` publish no 3.15 wheel. The focused tests above ran without Chroma. CI remains Python 3.11 and 3.12, where the full requirements file installs.

FIN-001 constants are owner-only and are no longer shown as a product match. FIN-013 treats a missing quarter as missing, and a killed Full replace restores from the recovery file on the next open. Unpriced holdings are out of allocation weights.

Still not started, because the source is absent or the row is deferred: the 2022 activity file (IMP-002), the screener prompt (RES-001), AI grounding (AI-004, AI-005, AI-008), the MVP walkthrough (UX-010), and Band F (IBKR sync, local models, targets, payments). Do not invent those.
