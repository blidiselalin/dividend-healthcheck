# 👑 DividendScope

**Intelligent dividend analytics and portfolio tracking for income investors.**

Research Dividend Kings and Aristocrats, track your holdings, monitor dividend income, and deploy to the cloud — all in one self-hosted Streamlit app backed by PostgreSQL.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/streamlit-1.42+-red.svg)](https://streamlit.io/)
[![PostgreSQL 16](https://img.shields.io/badge/postgresql-16-336791.svg)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED.svg)](https://docs.docker.com/compose/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Architecture Guardrails](#architecture-guardrails)
- [Installation at a Glance](#installation-at-a-glance)
- [Quick Start — Docker (recommended)](#quick-start--docker-recommended)
- [Local Development (no Docker)](#local-development-no-docker)
- [Authentication](#authentication)
- [Portfolio Management](#portfolio-management)
- [New user guide](#new-user-guide)
- [Market Data & Ingestion CLI](#market-data--ingestion-cli)
- [Scoring Framework](#scoring-framework)
- [Project Structure](#project-structure)
- [Configuration Reference](#configuration-reference)
- [Cloud Deployment (GCP)](#cloud-deployment-gcp)
- [Troubleshooting](#troubleshooting)

---

## Features

| Category | What you get |
|---|---|
| **Stock Research** | Dividend Kings & Aristocrats analysis, yield-channel charts, sector comparison, news & sentiment |
| **Portfolio Tracking** | Holdings, purchase journal, monthly deposits, realized/unrealized P&L |
| **Dividend Income** | Monthly income calendar, dividend receipt log, CAGR and growth trend |
| **Risk & Allocation** | Sector concentration, risk monitor, attention items (payout ratio, streak breaks), benchmark comparison |
| **Benchmark Comparison** | Portfolio total-return vs S&P 500, SCHD, Dow Jones, Nasdaq — same monthly purchases |
| **PDF Reports** | One-click research reports with score card and investment thesis |
| **Assistant** | In-app FAQ chatbot; optional Hugging Face LLM for broader replies |
| **Admin Panel** | Database administration, market library sync, schema migrations |
| **No API keys** | All market data from Yahoo Finance, SEC EDGAR, and Stooq — free public sources |

---

## Architecture

```
Browser → Caddy (HTTPS 443) → Streamlit :8501 → PostgreSQL 16
```

| Component | Technology | Role |
|---|---|---|
| **App** | Streamlit 1.42+ | UI, auth, API |
| **Database** | PostgreSQL 16 (Docker) | Users, portfolios, market library |
| **Auth** | Google OAuth (OIDC) via `streamlit[auth]` | Login, user isolation |
| **Market data** | `stock_documents` table (JSONB) | Shared S&P 500 library; hourly price refresh |
| **Price/dividend history** | `stock_price_history`, `stock_dividend_history` | Yield charts, income calendar |
| **Benchmark comparison** | `benchmark_price_history`, `benchmark_etf_info` | Portfolio vs S&P 500 / SCHD / Dow / Nasdaq |
| **Reverse proxy** | Caddy (host) | Auto-TLS via Let's Encrypt |

> **All portfolio data is user-scoped in PostgreSQL.** No SQLite or ChromaDB is used at runtime when `DATABASE_URL` is set.

## Architecture Guardrails

Use these conventions when extending the app so features remain fast, testable, and consistent:

- **One portfolio context per flow**: use `services.portfolio_context.create_portfolio_context()` for holdings + journal + dividends in the same request.
- **Service-first UI**: keep `ui/*` focused on rendering and state; move data orchestration and fallback logic to `services/*`.
- **Batch over per-symbol loops**: prefer `get_by_symbols()` / `load_documents()` style bulk fetches for holdings and screening views.
- **Cloud SQL as runtime source of truth**: when `DATABASE_URL` is set, avoid introducing new runtime SQLite/Chroma write paths.
- **Date parsing discipline**: parse DB values through `db.parsing` helpers to support both PostgreSQL and local SQLite tests.
- **Background-first UI**: heavy portfolio work (live prices, yield preload, dividend sync, vector linking) runs in **background threads** via `services/deferred_startup.py` + `services/background_jobs.py`. UI code should call `schedule_portfolio_reload()` — not block reruns with `reload_portfolio_session()` or synchronous `build_rows_with_cache(use_live_prices=True)`.
- **Single DB sync checkpoint**: `sync_portfolio_session_with_db()` runs once at app startup (`app.py`). Do not call it from every tab render.

### Portfolio UI runtime

Streamlit reruns stay responsive by separating **paint** from **reload**:

```
Browser rerun
  → sync_portfolio_session_with_db()     # fingerprint check; queues refresh if DB changed
  → hydrate_session_from_disk()          # restore per-user JSON cache when session is empty
  → apply_background_results()           # merge finished background jobs into session_state
  → schedule_startup_tasks()             # warm / dividend sync / yield preload on first open
  → UI reads st.session_state only       # no full portfolio rebuild on tab navigation
```

| Layer | Module | Role |
|---|---|---|
| **Session sync** | `services/portfolio_session.py` | Detect portfolio DB changes via `utils/portfolio_db.compute_portfolio_db_fingerprint()`; schedule background refresh |
| **Disk cache** | `services/portfolio_ui_cache.py` | Per-user `portfolio_ui_session.json` (rows, preload, risk summary, fingerprint) for instant startup |
| **Job queue** | `services/deferred_startup.py` | Schedule warm load, live reload, yield preload, dividend sync |
| **Job registry** | `services/background_jobs.py` | Thread-safe workers; results applied on the main Streamlit thread |
| **UI triggers** | `services/portfolio_refresh.py` | `schedule_portfolio_reload()` for sidebar/manage/section refresh; `reload_portfolio_session()` for tests/scripts only |
| **Progress** | `ui/sidebar_progress_panel.py` | Polls every 2s while jobs run; reruns when warm/live/yield/DB refresh completes |

**Background job kinds** (see `services/deferred_startup.py`):

| Job | When | What it does |
|---|---|---|
| `warm_portfolio` | Empty session, holdings in DB | Fast load from market library (no live API prices) |
| `yield_preload` | After fast load | Batch yield-channel charts for all holdings |
| `live_reload` | **Reload live data** button | Live prices + full analysis preload + risk rescan |
| `portfolio_db_refresh` | After edits or fingerprint drift | Re-read holdings from DB (library prices) |
| `dividend_sync` | Startup (≤ every 6h) | Sync received dividend receipts from market history |

**Caching:** month-to-date dividends use `cached_current_month_paid_dividends()` (keyed by DB fingerprint + date). Section tabs use `@st.cache_data` where appropriate (e.g. dividend growth, benchmark comparison).

---

## Installation at a Glance

Choose one path:

1. **Docker (recommended)** — fastest way to run the full app with PostgreSQL.
2. **Local development** — run Streamlit directly for feature work and tests.
3. **GCP VM** — production-style setup with HTTPS and update automation.

If you're unsure, start with **Docker Quick Start** below.

---

## Quick Start — Docker (recommended)

Requires [Docker Desktop](https://docs.docker.com/get-docker/) (or Docker + Docker Compose on Linux).

```bash
git clone https://github.com/blidiselalin/dividend-healthcheck.git
cd dividend-healthcheck
cp .env.example .env
# Edit .env and set a strong POSTGRES_PASSWORD
docker compose up -d --build
```

Open: **http://localhost:8501**

First-run market library load (recommended once):

```bash
docker compose exec dividendscope python ingest_data.py --ensure-sp500 --enrich-existing
```

Optional: complete historical tables sync if you want full yield/dividend history immediately:

```bash
docker compose exec dividendscope python ingest_data.py --sync-history-tables
```

> Migrations run automatically at container start via the entrypoint.

---

## Local Development (no Docker)

Use this for feature work and tests without running the full Docker stack.

```bash
git clone https://github.com/blidiselalin/dividend-healthcheck.git
cd dividend-healthcheck
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Without `DATABASE_URL`, local development uses fallback local storage paths. Production should use PostgreSQL via Docker/GCP.

Common local commands:

```bash
python -m pytest tests/ -m "not integration" -q --tb=short
python -m db --migrate
```

---

## Authentication

Authentication uses **Google OAuth (OIDC)** via `streamlit[auth]`. It is required in production and optional locally.

### Set up Google OAuth

1. [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Credentials** → **Create credentials** → **OAuth 2.0 Client ID**.
2. Application type: **Web application**.
3. Authorized redirect URI: `https://your-domain/oauth2callback` (or `http://localhost:8501/oauth2callback` locally).
4. Copy the **Client ID** and **Client Secret**.

### Configure Streamlit secrets

Create `.streamlit/secrets.toml` (gitignored):

```toml
[auth]
redirect_uri = "https://your-domain/oauth2callback"
cookie_secret = "a-random-string-at-least-32-chars"

[auth.providers.google]
client_id     = "YOUR_CLIENT_ID.apps.googleusercontent.com"
client_secret = "YOUR_CLIENT_SECRET"
```

### Access control

By default, anyone with a Google account can log in. To restrict to specific emails, use the **Admin panel** → **Access requests** feature in the sidebar.

### Demo / test mode

Without Google OAuth configured, the login screen offers **Continue as test user** — a demo workspace with sample holdings (KO, JNJ, O) and a **Test mode — quick tour** on Home. Useful for evaluating the app before setting up OAuth.

---

## New user guide

### Try before sign-up (Command Center)

Logged-out visitors see the **Dividend Command Center** — a full-width homepage, not a text landing page:

| Section | What it does |
|---|---|
| **Hero + search** | Add up to **3 tickers** to a session try-list (starts with KO, JNJ, O) |
| **Demo dashboard** | Next-12-month dividend forecast chart, annual income run-rate, upcoming payouts, safety alerts |
| **Feature cards** | Track income · Analyze safety · Forecast growth |
| **Sample stock report** | Yield, payout, streak, and safety score from the shared library |
| **Import options** | Manual (now), CSV and broker sync (planned) |
| **CTA** | **Create portfolio — Sign up with Google** — try-list holdings copy into the new account |

This matches the product story: **past dividends → current safety → future income**.

### After sign-up (authenticated Home)

### What DividendScope contains

| Area | Where in the app | What you get |
|---|---|---|
| **Portfolio snapshot** | Home | Total value, day change, P/L, dividends received this month, positions table (worst first — click a row for analysis) |
| **Holdings** | Home → section button | Full table, filters, yield zones, compare same-sector positions |
| **Dividend income** | Home → section button | Monthly calendar, cash received, upcoming ex-dates |
| **Dividend growth** | Home → section button | Per-share growth and trends across your holdings |
| **Purchase journal** | Home → section button | Buy dates, lots, share counts |
| **Deposits & benchmarks** | Home → section button | Monthly deposits, portfolio € value, comparison vs S&P 500 / SCHD / Dow / Nasdaq |
| **Research** | Home (S&P picker) | Analyze any S&P 500 symbol before you buy |
| **Risk & watchlists** | Sidebar | Buy opportunities, dividend timing, high-risk flags (after live reload) |
| **Manage portfolio** | Sidebar expander | Add/edit holdings, log purchases, monthly deposits |
| **Assistant** | Sidebar | FAQ and how-to (optional Hugging Face for broader chat) |

Your **holdings, journal, deposits, and receipts** are private to your account in PostgreSQL. **Market history** (prices, dividends, fundamentals) comes from a **shared S&P library** used by all users.

### Setup in four steps (first visit)

1. **Add your first ticker** — Sidebar → **Manage portfolio** → **Add ticker** (symbol, shares, average cost) → **Add to portfolio**
2. **Wait for background load** — Watch **Background tasks** in the sidebar; Home fills in from the shared library (usually seconds)
3. **Reload live data** (recommended) — Sidebar → **Reload live data** for today's prices, yield charts, and watchlists (runs in background)
4. **Explore** — Use section buttons on Home; click any ticker for full analysis

Optional later: **Purchase** and **Monthly evolution** tabs under Manage portfolio; **Refresh watchlists** for a fast risk rescan without new prices.

### Where to get help in the app

- **What is DividendScope?** expander on Home — purpose, what you manage, data sources
- **Getting started — step-by-step guide** on Home — progress checklist (dismiss when done)
- **Next step** caption under **Portfolio** in the sidebar
- **Assistant** — ask *getting started*, *reload live data*, *yield channels*, or a ticker symbol

---

## Portfolio Management

Once logged in, every user gets an isolated portfolio scoped to their account.

### Home & holdings overview

- **Home** shows a summary strip (value, day change, P/L, month dividends received) and a **positions table** sorted worst-first
- Click a ticker row to open full holding analysis (yield channel, fundamentals, journal)
- Portfolio state is restored from a **disk cache** on startup; heavy reloads run in the **Background tasks** sidebar panel
- **New users:** a **Getting started — step-by-step guide** on Home walks through add holding → background load → reload live data → explore tabs (sidebar shows the current next step)

### Reloading data

| Action | Behaviour |
|---|---|
| **Reload live data** (sidebar) | Queues a background `live_reload` — fetches live prices, rebuilds charts, refreshes watchlists |
| **Refresh watchlists** | Fast rescan from cached rows (no new prices) |
| **Manage portfolio** edits | Queues `portfolio_db_refresh` — views update in background after saves |
| **Per-tab Update** | Dashboard/holdings/dividends tabs queue live reload; journal/deposits clear section cache only |

The UI paints immediately from cache; numbers refresh when the background job completes (sidebar shows progress).

### Holdings & Purchase Journal

- Add holdings manually via the **Manage** panel or import from a CSV
- Each purchase is recorded in the journal with cost basis, quantity, and date
- The dashboard shows unrealized P&L, sector allocation, and market value

### Dividend Income

- **Monthly calendar** — upcoming ex-dates and estimated payments
- **Receipt log** — confirmed dividend payments with amounts
- **Growth chart** — income CAGR over time
- **Month received (Home / Dashboard)** — gross cash paid this month through today, recomputed from holdings + dividend history (Yahoo-aligned); cached per session

### Deposits & Benchmarks

- Log monthly deposits to track invested capital separately from gains
- Compare portfolio total return against S&P 500 benchmark

---

## Market Data & Ingestion CLI

Market data is shared across all users in the `stock_documents` PostgreSQL table. An hourly background job refreshes prices automatically.

### Market data sources

Enrichment runs through `data_ingestion/stock_enricher.py` in priority order:

| Source | API key? | Provides |
|---|---|---|
| **Yahoo Finance** (yfinance) | No | Price, dividends, fundamentals, history |
| **SEC EDGAR** | No | Company name, sector (SIC), margins, ROE, debt/equity |
| **Stooq** | No | Daily OHLCV history when Yahoo fails |

Providers only fill **missing** fields; existing data is never overwritten.

> SEC requests require a `User-Agent` header (SEC policy). The default is built in. Override for production:
> ```bash
> export SEC_EDGAR_USER_AGENT="DividendScope/1.0 (you@yourdomain.com)"
> ```

### Ingestion commands

```bash
# Populate S&P 500 universe (first run)
python ingest_data.py --ensure-sp500

# Enrich all stocks with live fundamentals (recommended after populate)
python ingest_data.py --enrich-existing

# Backfill price and dividend history
python ingest_data.py --backfill-history --backfill-limit 120

# Sync JSONB history into normalized tables (repeat until output shows synced=0)
python ingest_data.py --sync-history-tables

# Enrich specific symbols only
python ingest_data.py --enrich-existing --symbols KO,JNJ,PG

# Add individual symbols to the library
python ingest_data.py --add-symbols MSFT,AAPL

# Refresh prices for all symbols in the library
python ingest_data.py --refresh-prices

# Trigger a single hourly-update cycle (prices + thin-row backfill)
python ingest_data.py --hourly-update

# Sync portfolio holdings data into the market library
python ingest_data.py --sync-portfolio

# Database utilities
python ingest_data.py --stats                    # Show document counts
python ingest_data.py --list-kings               # List all Dividend Kings in library
python ingest_data.py --search "high yield tech" # Semantic search
python ingest_data.py --export backup.json       # Export library to JSON
python ingest_data.py --import backup.json       # Restore from JSON
python ingest_data.py --export-snapshot          # Export snapshot for offline use
```

### Download commands (raw data files)

```bash
# Download Dividend Kings + Aristocrats data
python download_data.py

# Download specific symbols
python download_data.py --symbols KO JNJ PG

# Skip price history (faster)
python download_data.py --no-prices --no-history

# Download then ingest in one step
python download_data.py --run-ingestion
```

---

## Scoring Framework

Each stock receives a composite 0–100 score based on dividend quality factors.

| Factor | Weight | Description |
|---|---|---|
| Dividend Streak | 20% | Consecutive years of increases (50+ = max) |
| Dividend Safety | 15% | Payout ratio and coverage ratio |
| Dividend Yield | 15% | Current yield (2.5–4.5% is the optimal range) |
| Dividend Growth | 15% | 5-year CAGR of dividend increases |
| Valuation | 10% | P/E ratio and price vs. 52-week high |
| Financial Strength | 10% | Debt/Equity, current ratio |
| Profitability | 10% | ROE, profit margins |
| Size / Stability | 5% | Market cap (larger = more stable) |

### Selection workflow (high level)

Use this order to keep dividend decisions consistent:

1. **Income quality first** — check yield, payout ratio, and dividend safety together.
2. **Durability second** — verify streak length and 5Y dividend growth.
3. **Valuation third** — review P/E and distance from 52-week high.
4. **Balance check** — use score composition to confirm strength is not coming from a single category.

### Recommendations

| Score | Label |
|---|---|
| 80–100 | **STRONG BUY** |
| 65–79 | **BUY** |
| 50–64 | **ACCUMULATE** |
| 35–49 | **HOLD** |
| <35 | **AVOID** |

### Dividend Yield Channels

Based on Geraldine Weiss's methodology: yield is the most honest valuation signal for dividend stocks.

| Zone | Yield percentile | Signal |
|---|---|---|
| 💎 Deep Value | 90th+ | Strong Buy |
| 🟢 Value | 75th–90th | Buy |
| 🟡 Fair Value | 25th–75th | Hold / DCA |
| 🟠 Caution | 10th–25th | Wait |
| 🔴 Expensive | <10th | Avoid / Trim |

### Dividend Tiers

| Tier | Consecutive Years | Badge |
|---|---|---|
| King | 50+ | 👑 |
| Aristocrat | 25–49 | 🏆 |
| Achiever | 10–24 | ⭐ |
| Contender | 5–9 | 📈 |
| Starter | <5 | 🌱 |

---

## Project Structure

```
dividend-healthcheck/
├── app.py                          # Streamlit entry point
├── config.py                       # Stock lists, scoring weights, thresholds
├── ingest_data.py                  # Market library ingestion CLI
├── download_data.py                # Public data downloader
├── requirements.txt                # Python dependencies
│
├── auth/                           # Authentication
│   ├── user_store.py               # User creation and lookup
│   ├── user_context.py             # Current-session user helpers
│   ├── access_requests.py          # Allow-list gate for new signups
│   ├── settings.py                 # OAuth / allow-list config (env + secrets.toml)
│   ├── login_view.py               # Login page UI
│   ├── demo_portfolio.py           # Read-only demo portfolio (no login required)
│   └── migration.py                # Legacy user data migration helpers
│
├── db/                             # PostgreSQL / SQLite data layer
│   ├── __main__.py                 # `python -m db --migrate` CLI
│   ├── connection.py               # Connection pool, schema migrations
│   ├── parsing.py                  # Date/type helpers for DB rows
│   ├── portfolio_scope.py          # Per-user DB scope helpers
│   ├── benchmark_store.py          # Benchmark ETF price history + metadata
│   ├── postgres_market_store.py    # Stock documents CRUD
│   └── postgres_market_history_store.py  # Price & dividend history tables
│
├── migrations/                     # Incremental SQL migration files
│   ├── 001_initial.sql             # Core schema (users, holdings, journal, market docs)
│   ├── 002_dividend_receipts.sql   # Dividend receipt log
│   ├── 003_stock_market_history.sql# Price & dividend history tables
│   ├── 004_benchmark_price_history.sql  # Benchmark ETF price history + metadata
│   └── 005_holdings_tracking_since_and_indexes.sql  # dividend_tracking_since + journal index
│
├── models/
│   └── stock.py                    # StockData and DividendHistory dataclasses
│
├── services/
│   ├── enhanced_stock_service.py   # DB-first, API-fallback orchestration
│   ├── stock_analysis_service.py   # Full per-symbol analysis pipeline
│   ├── stock_history_backfill.py   # Backfill price/dividend history from Yahoo
│   ├── portfolio_context.py        # Shared portfolio store factory
│   ├── portfolio_service.py        # Core holdings/journal/deposits store
│   ├── portfolio_management_service.py   # Add/edit/remove holdings
│   ├── portfolio_details_service.py      # Holdings enrichment with live prices
│   ├── portfolio_holdings_summary.py     # Value/P&L strip
│   ├── portfolio_holding_detail_service.py  # Per-symbol deep-dive
│   ├── portfolio_allocation_service.py   # Sector and market-cap breakdown
│   ├── portfolio_benchmark_service.py    # Portfolio vs benchmark ETF comparison
│   ├── portfolio_dividend_calendar.py    # Upcoming ex-dates and payments
│   ├── portfolio_dividend_income_service.py  # Income CAGR and growth charts
│   ├── portfolio_dividend_growth_service.py  # Per-symbol growth trend
│   ├── portfolio_dividend_sync_service.py    # Sync dividend receipts from market data
│   ├── portfolio_month_dividends.py      # Monthly income totals + session-cached month received
│   ├── portfolio_position_table.py       # Home positions table (concerns, sort worst-first)
│   ├── portfolio_risk_monitor_service.py # Risk snapshot (attention items + cache)
│   ├── portfolio_attention_service.py    # Attention rules (high payout, streak breaks…)
│   ├── portfolio_analysis_preload.py     # Batch preload yield charts for all holdings
│   ├── guest_playground.py         # Pre-login try-list (max 3 tickers, session-only)
│   ├── portfolio_refresh.py             # schedule_portfolio_reload + sync reload (tests)
│   ├── portfolio_ui_cache.py            # JSON session cache + hydrate/warm/fast/live payloads
│   ├── portfolio_session.py             # DB fingerprint sync + holdings cache helpers
│   ├── portfolio_vector_sync.py         # Sync holdings into shared market library
│   ├── portfolio_zone_overview.py       # Yield-zone summary (Weiss methodology)
│   ├── portfolio_deposits_service.py    # Monthly deposit tracking
│   ├── portfolio_purchase_journal_service.py  # Purchase journal views and charts
│   ├── portfolio_dashboard_service.py   # Dashboard orchestration
│   ├── analysis_evidence.py             # Data-source evidence overlay
│   ├── scoring.py                       # 0–100 dividend scoring engine
│   ├── news_service.py                  # News aggregation and sentiment
│   ├── report_generator.py              # PDF report generation
│   ├── yield_channel_chart.py           # "Dividends Don't Lie" chart builder
│   ├── chatbot_service.py               # FAQ + optional Hugging Face assistant
│   ├── hourly_market_update.py          # Hourly background price refresh job
│   ├── price_refresh_scheduler.py       # Background scheduler for price refresh
│   ├── db_price_refresh.py              # Price update helper (writes to DB)
│   ├── db_admin_service.py              # Admin operations (validate, sync, stats)
│   ├── live_price.py                    # Fetch live prices on top of DB snapshots
│   ├── shared_market_db.py              # Shared market library access helpers
│   ├── market_library_migration.py      # One-time Chroma→Postgres import
│   ├── snapshot_sync_service.py         # JSONB→normalized table sync
│   ├── sector_service.py                # Sector comparison and peer ranking
│   ├── sp500_peers_service.py           # S&P 500 peer selection for portfolio
│   ├── dividend_timing.py               # Dividend timing rules
│   ├── deferred_startup.py              # Defer heavy init to background threads
│   ├── background_jobs.py               # Long-running background task wrappers
│   └── vectordb_service.py              # Chroma/fallback store service (dev only)
│
├── data_ingestion/                 # Market library ingestion pipeline
│   ├── stock_enricher.py           # Yahoo + SEC EDGAR + Stooq enrichment
│   ├── yfinance_enricher.py        # yfinance-specific enrichment helpers
│   ├── pipeline.py                 # CLI orchestration
│   ├── vector_store.py             # ChromaDB wrapper (dev/test fallback)
│   ├── portfolio_store.py          # Holdings store (SQLite local / Postgres cloud)
│   ├── purchase_journal_store.py   # Purchase journal store
│   ├── dividend_receipt_store.py   # Dividend receipt log store
│   ├── dividend_income_store.py    # Monthly net dividend income store
│   ├── deposits_store.py           # Monthly deposit store
│   ├── dividend_universe.py        # Dividend Kings/Aristocrats universe helpers
│   ├── sp500_universe.py           # S&P 500 constituent list helpers
│   ├── benchmark_purchases_seed.py # Benchmark ETF monthly share purchase seed data
│   ├── providers/                  # Per-source adapters (Yahoo, SEC, Stooq, snapshot)
│   └── ...                         # Downloaders, seed data, fetch utilities
│
├── ui/                             # Streamlit pages and components
│   ├── views.py                    # Single-stock and full-analysis pages
│   ├── portfolio_home.py           # Portfolio welcome, summary, positions table
│   ├── command_center_home.py      # Pre-login Dividend Command Center UI
│   ├── portfolio_onboarding.py     # Post-sign-up onboarding checklist
│   ├── portfolio_details_view.py   # Holdings, journal, income, benchmark views
│   ├── portfolio_positions_table.py # Home positions table UI (row click → analysis)
│   ├── portfolio_sidebar.py        # Sidebar navigation, reload, manage entry
│   ├── portfolio_manage_panel.py   # Add/edit/remove holdings UI
│   ├── portfolio_risk_panel.py     # Risk monitor and attention panel
│   ├── portfolio_summary.py        # Holdings value/P&L summary strip
│   ├── admin_page.py               # Database admin and market library sync
│   ├── db_admin_panel.py           # Low-level DB admin tools
│   ├── sp500_research_picker.py    # Pick any S&P 500 symbol for full analysis
│   ├── analysis_evidence.py        # Data-source evidence overlay
│   ├── chatbot_widget.py           # Sidebar assistant widget
│   ├── dividend_timing_display.py  # Upcoming / paid dividend styled tables
│   ├── charts.py                   # Shared chart utilities
│   ├── components.py               # Reusable UI components
│   ├── sidebar_progress_panel.py   # Background job progress display
│   ├── market_library_cache.py     # Market library cache status display
│   ├── auth_account_panel.py       # Account settings and logout
│   ├── access_request_panel.py     # Access request management UI
│   ├── app_about.py                # About page (purpose, data sources, usage)
│   └── theme.py                    # Visual theme helpers and palette
│
├── utils/                          # Shared helpers (non-UI)
│   ├── portfolio_db.py             # Portfolio DB fingerprint + holding count helpers
│   ├── dividend_amounts.py         # Dividend normalization and frequency helpers
│   └── ...                         # yfinance config, chart theme, parsing helpers
│
├── deploy/gcp/                     # GCP-specific scripts (bootstrap, Caddy, HTTPS)
├── scripts/                        # update_cloud_docker.sh, docker-entrypoint.sh
└── tests/                          # pytest suite (unit + integration)
    ├── conftest.py                 # Shared fixtures; SQLite backend for unit tests
    ├── support/                    # Test helpers (market fixtures, postgres mock)
    └── integration/                # Live-Postgres integration tests (CI only)
```

**Persistent data** (Docker volume `dividendscope-persistent-data → /data`, never committed):

```
/data/
├── postgres/     PostgreSQL cluster (all user and market data)
├── users/        legacy SQLite import source (one-time migration only)
└── vectordb/     legacy Chroma import source (one-time migration only)
```

---

## Configuration Reference

### Environment variables (`.env`)

```bash
# Required in production — change before first deploy
POSTGRES_USER=dividendscope
POSTGRES_PASSWORD=change-me-in-production
POSTGRES_DB=dividendscope

# Built by Docker Compose from the vars above (do not set manually in compose)
# DATABASE_URL=******postgres:5432/dividendscope

# Optional: SEC EDGAR User-Agent (SEC policy requires identification — not an API key)
SEC_EDGAR_USER_AGENT=DividendScope/1.0 (you@yourdomain.com)

# Optional: Sidebar assistant — FAQ works without keys; HF enables broader chat (server-side only)
DIVIDENDSCOPE_CHATBOT_ENABLED=1
HUGGINGFACE_API_KEY=hf_...        # Server-side only — never expose to the browser
DIVIDENDSCOPE_CHATBOT_MODEL=facebook/blenderbot-400M-distill

# Optional: Data directory overrides
DIVIDENDSCOPE_DATA_DIR=/data      # Override default data root (default: /data in Docker)

# Optional: Market library behaviour
DIVIDENDSCOPE_HISTORY_REFRESH_HOURS=6     # Hours between automatic history refresh (default: 6)
DIVIDENDSCOPE_AUTO_BACKFILL_ON_LOAD=1     # Backfill thin rows on container start (default: 1)
DIVIDENDSCOPE_SKIP_LEGACY_IMPORT=0        # Skip one-time Chroma→Postgres import (default: 0)

# Optional: Price refresh scheduler
DIVIDENDSCOPE_DISABLE_PRICE_SCHEDULER=0  # Disable background price refresh (default: 0)
DIVIDENDSCOPE_PRICE_REFRESH_SECONDS=3600 # Override price refresh interval in seconds

# Optional: Auth overrides (also configurable via .streamlit/secrets.toml)
DIVIDENDSCOPE_AUTH_DISABLE=0             # Bypass auth for local dev (default: 0)
DIVIDENDSCOPE_DEV_EMAIL=you@example.com  # Auto-login email when auth is disabled
DIVIDENDSCOPE_ADMIN_EMAILS=admin@x.com   # Comma-separated admin email allow-list
DIVIDENDSCOPE_ALLOWED_EMAILS=            # Comma-separated email allow-list (empty = allow all)

# Optional: Logging
DIVIDENDSCOPE_LOG_LEVEL=INFO             # Log level (DEBUG / INFO / WARNING / ERROR)
```

Copy `.env.example` to `.env` to get started.

### Scoring and stock universe (`config.py`)

```python
DIVIDEND_KINGS = ["KO", "JNJ", "PG", ...]    # 50+ year streak stocks
DIVIDEND_ARISTOCRATS = ["ABBV", "ADM", ...]   # 25+ year streak stocks

RECOMMENDATION_THRESHOLDS = {
    "strong_buy": 80, "buy": 65, "accumulate": 50, "hold": 35,
}

API_DELAY_SECONDS = 0.2      # Increase if hitting rate limits
DEFAULT_STALENESS_DAYS = 7   # Days before re-fetching from API
```

---

## Cloud Deployment (GCP)

The recommended production setup is a **Google Compute Engine VM** running Docker Compose with Caddy for HTTPS.

### Recommended VM instances

| Use case | Machine type | vCPU | RAM | Approx. cost / month |
|---|---|---|---|---|
| Personal / trial | **e2-micro** | 2 (shared) | 1 GB | ~$7 ¹ |
| **Recommended** | **e2-small** | 2 (shared) | 2 GB | ~$14 |
| Small team (3–10 users) | **e2-medium** | 2 (shared) | 4 GB | ~$27 |
| Larger team / heavy ingestion | **e2-standard-2** | 2 | 8 GB | ~$49 |

> ¹ e2-micro is free-tier eligible (1 per account, `us-*` regions). It may be slow during initial ingestion. Upgrade to e2-small if the app feels sluggish.
>
> All estimates are for `us-central1`, sustained-use discounts applied. Add ~$2–4/month for a 30 GB boot disk. Costs are covered by the GCP $300 free trial (90 days).

**Disk:** 30 GB Balanced persistent disk is sufficient for most deployments. Use 50 GB if you plan to ingest full S&P 500 history.

### Deploy (quick path)

```bash
# 1) Bootstrap Docker on Ubuntu 22.04
curl -fsSL https://raw.githubusercontent.com/blidiselalin/dividend-healthcheck/main/deploy/gcp/vm-bootstrap.sh | bash
# then log out and back in so docker group membership applies

# 2) Clone and configure
git clone https://github.com/blidiselalin/dividend-healthcheck.git
cd dividend-healthcheck
cp .env.example .env
# edit POSTGRES_PASSWORD in .env

# 3) Start app + run migrations + ingest data
./scripts/update_cloud_docker.sh --ingest

# 4) Enable HTTPS (domain must point to VM IP)
sudo ./deploy/gcp/setup-https-caddy.sh
```

### Update an existing deployment

```bash
cd ~/dividend-healthcheck
./scripts/update_cloud_docker.sh
```

For a full deployment walkthrough including DNS, static IP, OAuth redirect URIs, and Caddy configuration, see **[DEPLOY-GCP.md](DEPLOY-GCP.md)**.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `ModuleNotFoundError` | `pip install -r requirements.txt` |
| App starts but shows no data | Check internet; yfinance needs network access |
| Postgres connection refused | `docker compose ps` — wait for the `healthy` status on the `postgres` service |
| `🌐 Public API (DB empty)` in sidebar | Run `docker compose exec dividendscope python ingest_data.py --ensure-sp500 --enrich-existing` |
| Slow first-run ingestion | Normal — 15–20 min for full S&P 500 enrichment; market data is cached afterwards |
| Portfolio empty briefly after login | Normal — wait for **Background tasks** → *Loading portfolio*; disk cache fills on first successful load |
| Numbers stale after editing holdings | Wait for *Updating portfolio* in sidebar, or click **Reload live data** |
| `Failed to fetch dynamically imported module` (Streamlit JS) | Hard-refresh the browser (Ctrl+Shift+R). Production Caddy sets `no-cache` on `/static/*` — redeploy Caddyfile if needed |
| Benchmark chart shows no data | Run `python ingest_data.py --refresh-prices` to fetch benchmark ETF history |
| `chromadb` import errors | `pip install chromadb>=0.4.22`; app works without it (API-only mode) |
| PDF export fails | `pip install reportlab` (included in `requirements.txt`) |
| News section empty | `pip install feedparser` (optional); Yahoo Finance news still works without it |
| Port 8501 already in use | `streamlit run app.py --server.port 8502` |
| `Server: nginx` on HTTPS domain | Run `sudo ./deploy/gcp/setup-https-caddy.sh` on VM (replaces nginx with Caddy) |
| Container name already in use | `docker rm -f dividendscope && docker compose up -d --build` |
| Out of memory on VM | Upgrade to e2-small (2 GB) or e2-medium (4 GB) |
| Google login redirect mismatch | Add the exact redirect URI to your Google OAuth 2.0 client and to `.streamlit/secrets.toml` |
| Schema out of date | Run `python -m db --migrate` (or restart the container — entrypoint does this automatically) |

---

**Disclaimer:** DividendScope is for educational and informational purposes only. It is not financial advice. Always conduct your own research and consult a qualified professional before making investment decisions.
