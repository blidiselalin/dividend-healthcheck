# 👑 DividendScope

**Intelligent financial analytics for dividend investors.**

Analyze S&P 500 and Dividend Kings (50+ years of consecutive increases), track your personal portfolio, assess dividend safety, and discover high-quality income opportunities — backed by a PostgreSQL database with live hourly market data.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/streamlit-1.42+-red.svg)](https://streamlit.io/)
[![PostgreSQL 16](https://img.shields.io/badge/postgresql-16-blue.svg)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED.svg)](https://docs.docker.com/compose/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Table of Contents

- [What's New](#whats-new)
- [Prerequisites](#prerequisites)
- [Quick Start — Docker Compose](#quick-start--docker-compose)
- [Local Dev — Without Docker](#local-dev--without-docker)
- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Configuration & Environment Variables](#configuration--environment-variables)
- [Market Data Sources](#market-data-sources)
- [Ingestion CLI Reference](#ingestion-cli-reference)
- [Scoring Framework](#scoring-framework)
- [Deploy to Google Cloud](#deploy-to-google-cloud)
- [Troubleshooting](#troubleshooting)

---

## What's New

| Area | Change |
|------|--------|
| **Database** | PostgreSQL 16 replaces ChromaDB as the primary store. All user, portfolio, and market data live in Postgres. |
| **Portfolio tracking** | Full per-user portfolio: holdings, purchase journal, monthly deposits, dividend receipts, income calendar, risk monitor, and benchmark comparison. |
| **Multi-user auth** | Google OIDC login via `streamlit[auth]`. Admin-controlled access requests. Demo portfolio for unauthenticated preview. |
| **S&P 500 library** | Shared `stock_documents` table covers the full S&P 500. Hourly cron refreshes live prices and re-enriches stale records. |
| **Price & dividend history** | `stock_price_history` and `stock_dividend_history` tables power yield-channel charts and monthly income exposure. |
| **Background jobs** | Startup tasks and a 5-minute price-refresh scheduler run in the background so the UI stays responsive. |
| **In-app assistant** | Sidebar chatbot: curated FAQ + optional Hugging Face server-side inference (`HUGGINGFACE_API_KEY`). |
| **Admin panel** | Database admin page: run validation, sync history tables, view document coverage. |

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| **Docker + Compose** | 24+ / v2+ | Recommended path — everything runs in containers |
| **Python** | 3.10+ | For local dev without Docker |
| Internet access | — | Required for live market data (Yahoo Finance, SEC EDGAR, Stooq) |

> **No API keys required.** All market data comes from free public sources.

---

## Quick Start — Docker Compose

The recommended way to run DividendScope. Starts a PostgreSQL 16 container and the Streamlit app in one command.

**Step 1 — Clone the repo**

```bash
git clone https://github.com/blidiselalin/dividend-healthcheck.git
cd dividend-healthcheck
```

**Step 2 — Configure environment**

```bash
cp .env.example .env
# Edit .env → set a strong POSTGRES_PASSWORD
```

**Step 3 — Start the stack**

```bash
docker compose up -d --build
```

**Step 4 — Build the market library** *(first time, ~15–25 min)*

```bash
docker compose exec -T dividendscope python ingest_data.py --ensure-sp500
docker compose exec -T dividendscope python ingest_data.py --enrich-existing
```

Open **http://localhost:8501** in your browser.

> The sidebar shows **Shared S&P library: N tickers · S&P X/500** once ingest is complete. All persistent data lives in the Docker volume `dividendscope-persistent-data` and survives rebuilds.

> ⚠️ **Never run** `docker compose down -v` — the `-v` flag deletes the data volume.

---

## Local Dev — Without Docker

Use this for development or quick experiments. The app falls back to ChromaDB + SQLite when `DATABASE_URL` is not set.

```bash
# 1. Create a virtual environment
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) set a custom data directory
export DIVIDENDSCOPE_DATA_DIR=~/.dividendscope/data

# 4. Launch
streamlit run app.py
```

On first launch the sidebar shows `🌐 Public API`. Populate the local store to speed things up:

```bash
python ingest_data.py --ensure-sp500 --enrich-existing
```

### Running Tests

```bash
python -m pytest tests/ -m "not integration"
```

Tests run against SQLite (no live Postgres required) via `PYTEST_USE_SQLITE=1` set in `tests/conftest.py`.

---

## Features

### Stock Research

| Feature | Description |
|---|---|
| **Single-stock analysis** | Prime Metrics panel, Investment Thesis, Sector Comparison, Yield Channel chart, News & Sentiment, PDF export |
| **S&P 500 picker** | Browse the full S&P 500 with dividend scores, yield, and streak |
| **All Dividend Kings** | Bulk analysis with filters, sortable table, CSV / PDF export |
| **Yield Channels** | "Dividends Don't Lie" chart (Geraldine Weiss methodology) — 5-zone valuation signal |
| **News & Sentiment** | Yahoo Finance + Google News RSS headlines with sentiment scoring — no API key needed |
| **PDF Reports** | Professional research report per stock (score card, thesis, metrics) |

### Portfolio Tracking

| Feature | Description |
|---|---|
| **Holdings** | Add/remove positions; live price and yield refresh every 5 minutes |
| **Purchase Journal** | Record buy lots with date and price for cost-basis tracking |
| **Monthly Deposits** | Log cash deposits to track contribution history |
| **Dividend Receipts** | Record received dividends; net income rolled up to `net_dividends` |
| **Dividend Calendar** | Month-by-month income calendar with projected vs. actual receipts |
| **Dividend Growth** | CAGR of income per holding over time |
| **Risk Monitor** | Concentration, sector diversification, and payout risk alerts |
| **Benchmark Comparison** | Portfolio income vs. a benchmark (e.g. S&P 500 equivalent) |
| **Zone Overview** | Yield-channel zone distribution across all holdings |
| **Attention Service** | Flags holdings that need attention (yield drop, payout spike, etc.) |

### Infrastructure

| Feature | Description |
|---|---|
| **Multi-user auth** | Google OIDC via `streamlit[auth]`; admin access-request approval |
| **Demo portfolio** | Unauthenticated users see a read-only demo — no login required to explore |
| **Hourly market refresh** | Cron job on the VM updates live prices and re-enriches up to 40 stale symbols per run |
| **Background jobs** | 5-minute price-refresh scheduler + deferred startup tasks keep the UI fast |
| **Admin panel** | Sidebar → Admin: database validation, history-table sync, document coverage view |
| **In-app assistant** | Sidebar chatbot with curated FAQ; optional HuggingFace for broader replies (server-side only) |

---

## Architecture

```
Browser ──HTTPS──▶ Caddy (host, port 443)
                       │ reverse proxy
                       ▼
                 Streamlit app (Docker, 127.0.0.1:8501)
                       │
              ┌────────┴────────┐
              │                 │
       PostgreSQL 16       ChromaDB / SQLite
     (Docker, primary)    (local dev / tests)
```

**Data ownership in PostgreSQL:**

| Data | Tables | Scoped by |
|------|--------|-----------|
| Users & access requests | `users`, `access_requests` | global |
| Holdings | `holdings` | `user_id` |
| Purchases | `purchase_journal` | `user_id` |
| Deposits | `monthly_deposits` | `user_id` |
| Net dividends | `net_dividends` | `user_id` |
| Dividend receipts | `dividend_receipts` | `user_id` + symbol |
| Shared S&P library | `stock_documents` | symbol |
| Price history | `stock_price_history` | symbol |
| Dividend history | `stock_dividend_history` | symbol |

Schema migrations are in `migrations/` and applied automatically on container start via `python -m db --migrate`.

---

## Project Structure

```
dividend-healthcheck/
├── app.py                          # Streamlit entry point
├── config.py                       # Stock universe, scoring weights, thresholds
├── ingest_data.py                  # Market library ingestion CLI
├── download_data.py                # Legacy CSV downloader (optional)
├── requirements.txt                # Python dependencies
│
├── auth/                           # Authentication & user management
│   ├── login_view.py               # Google OIDC login page
│   ├── user_store.py               # User CRUD (PostgreSQL)
│   ├── access_requests.py          # Admin-approved access flow
│   ├── settings.py                 # Auth feature flags
│   └── demo_portfolio.py           # Read-only demo for unauthenticated users
│
├── db/                             # Database layer
│   ├── connection.py               # PostgreSQL connection pool; ensure_schema()
│   ├── postgres_market_store.py    # stock_documents CRUD + dual-write
│   ├── postgres_market_history_store.py  # price/dividend history tables
│   ├── parsing.py                  # Safe date/decimal parsing from DB rows
│   └── migrations/                 # → see migrations/ at repo root
│
├── migrations/                     # Incremental SQL migrations (001, 002, 003 …)
│
├── services/                       # Business logic
│   ├── portfolio_context.py        # Shared context: portfolio + journal stores
│   ├── portfolio_service.py        # Holdings lifecycle
│   ├── portfolio_dashboard_service.py
│   ├── portfolio_dividend_income_service.py
│   ├── portfolio_dividend_calendar.py
│   ├── portfolio_risk_monitor_service.py
│   ├── portfolio_benchmark_service.py
│   ├── portfolio_attention_service.py
│   ├── scoring.py                  # 0–100 dividend scoring engine
│   ├── stock_analysis_service.py   # Single-stock deep analysis
│   ├── enhanced_stock_service.py   # DB-first, API-fallback orchestration
│   ├── shared_market_db.py         # Shared S&P library access
│   ├── hourly_market_update.py     # Hourly refresh logic
│   ├── price_refresh_scheduler.py  # 5-min background price refresh
│   ├── news_service.py             # News aggregation + sentiment
│   ├── report_generator.py         # PDF report builder
│   ├── yield_channel_chart.py      # Yield-channel chart (Geraldine Weiss)
│   ├── chatbot_service.py          # FAQ + optional HuggingFace chatbot
│   └── …                           # (additional portfolio sub-services)
│
├── ui/                             # Streamlit UI components
│   ├── views.py                    # Single stock / Full analysis pages
│   ├── portfolio_home.py           # Portfolio dashboard
│   ├── portfolio_details_view.py   # Per-holding detail page
│   ├── portfolio_sidebar.py        # Portfolio navigation sidebar
│   ├── portfolio_risk_panel.py     # Risk monitor panel
│   ├── admin_page.py               # Admin database panel
│   ├── chatbot_widget.py           # Sidebar assistant widget
│   ├── sp500_research_picker.py    # S&P 500 browser
│   ├── theme.py                    # App-wide theme & CSS injection
│   └── …                           # (additional panels and charts)
│
├── data_ingestion/                 # Market data pipeline
│   ├── stock_enricher.py           # Multi-source enricher (Yahoo + SEC + Stooq)
│   ├── pipeline.py                 # Ingestion orchestration
│   ├── vector_store.py             # ChromaDB wrapper (local dev / tests)
│   ├── portfolio_store.py          # Portfolio SQLite store (local dev)
│   └── purchase_journal_store.py   # Journal SQLite store (local dev)
│
├── models/
│   └── stock.py                    # StockData and DividendHistory dataclasses
│
├── scripts/
│   ├── docker-entrypoint.sh        # Container startup: migrate → import → start
│   ├── hourly_market_refresh.sh    # Cron wrapper for hourly update
│   ├── install_hourly_cron.sh      # Installs the cron job on the VM
│   ├── update_cloud_docker.sh      # VM deploy script (git pull + rebuild)
│   └── deploy_from_local.sh        # Deploy from local Mac to VM via rsync
│
├── deploy/gcp/                     # GCP-specific deploy files
│   ├── vm-bootstrap.sh             # One-time VM setup (Docker, clone)
│   ├── setup-https-caddy.sh        # Install Caddy + Let's Encrypt TLS
│   └── Caddyfile                   # Caddy reverse-proxy config
│
├── tests/                          # 80+ test files
│   ├── conftest.py                 # PYTEST_USE_SQLITE=1 (no live Postgres)
│   └── integration/                # Integration tests (live Postgres in CI)
│
└── docker-compose.yml              # Postgres 16 + app; shared volume
```

**Persistent data** (Docker volume `dividendscope-persistent-data`, mounted at `/data`):

```
/data/
├── postgres/        ← PostgreSQL cluster (primary store)
├── vectordb/        ← Legacy Chroma (import source only)
└── users/           ← Legacy per-user SQLite (import source only)
```

---

## Configuration & Environment Variables

### `config.py`

Tunable parameters for the stock universe and scoring:

```python
DIVIDEND_KINGS = ["KO", "JNJ", "PG", ...]       # 50+ year streak stocks
DIVIDEND_ARISTOCRATS = ["ABBV", "ADM", ...]      # 25+ year streak stocks

RECOMMENDATION_THRESHOLDS = {
    "strong_buy": 80, "buy": 65, "accumulate": 50, "hold": 35
}

API_DELAY_SECONDS = 0.2      # Rate-limit pause between API calls
DEFAULT_STALENESS_DAYS = 7   # Re-fetch after this many days
```

### Environment Variables (`.env` / Docker Compose)

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | *(set by compose)* | PostgreSQL connection string — enables Postgres mode |
| `POSTGRES_PASSWORD` | `change-me-in-production` | **Change before first deploy** |
| `DIVIDENDSCOPE_DATA_DIR` | `/data` (Docker) / `~/.dividendscope/data` (local) | Root data directory |
| `SEC_EDGAR_USER_AGENT` | `DividendScope/1.0 (…)` | Required by SEC policy (not a secret) |
| `DIVIDENDSCOPE_CHATBOT_ENABLED` | `1` | Set `0` to disable the sidebar assistant |
| `HUGGINGFACE_API_KEY` | *(none)* | Enables broader chatbot replies (server-side only) |
| `DIVIDENDSCOPE_LOG_LEVEL` | `INFO` | Set `DEBUG` for verbose container logs |

Copy `.env.example` → `.env` and set at minimum `POSTGRES_PASSWORD` before first deploy.

---

## Market Data Sources

Enrichment runs through `data_ingestion/stock_enricher.py` in priority order (providers fill only **missing** fields):

| Source | API key? | Provides |
|--------|----------|---------|
| **Yahoo Finance** (yfinance) | No | Price, dividends, fundamentals, history |
| **SEC EDGAR** | No | Company name, sector (SIC), margins, ROE, debt/equity |
| **Stooq** | No | Daily OHLCV history when Yahoo history fails |

---

## Ingestion CLI Reference

### Market library

```bash
# Populate S&P 500 symbols (skips existing)
python ingest_data.py --ensure-sp500

# Enrich all symbols with live fundamentals from yfinance
python ingest_data.py --enrich-existing

# Enrich specific symbols only
python ingest_data.py --enrich-existing --symbols KO,JNJ,PG

# Backfill price + dividend history (run after initial ingest)
python ingest_data.py --backfill-history --backfill-limit 120

# Sync JSONB history arrays → normalized history tables (repeat until synced=0)
python ingest_data.py --sync-history-tables

# Hourly update (prices + re-enrich up to 40 stale docs)
python ingest_data.py --hourly-update

# Statistics
python ingest_data.py --stats
python ingest_data.py --list-kings
python ingest_data.py --search "high yield consumer"
```

### Database utilities

```bash
# Export / import / clean
python ingest_data.py --export backup.json
python ingest_data.py --import backup.json
python ingest_data.py --consolidate    # Remove duplicates
python ingest_data.py --fix-values     # Fix invalid data
python ingest_data.py --clear          # Wipe the library

# Schema migrations (applied automatically on container start)
python -m db --migrate
```

---

## Scoring Framework

| Factor | Weight | Description |
|---|---|---|
| Dividend Streak | 20% | Consecutive years of increases (50+ = max) |
| Dividend Safety | 15% | Payout ratio and coverage ratio |
| Dividend Yield | 15% | Current yield (2.5–4.5% optimal range) |
| Dividend Growth | 15% | 5-year CAGR of dividend increases |
| Valuation | 10% | P/E ratio and price vs. 52-week high |
| Financial Strength | 10% | Debt/Equity, current ratio |
| Profitability | 10% | ROE, profit margins |
| Size / Stability | 5% | Market cap (larger = more stable) |

### Recommendation Thresholds

| Score | Label | Meaning |
|---|---|---|
| 80–100 | **STRONG BUY** | Excellent across all factors |
| 65–79 | **BUY** | Strong fundamentals, good value |
| 50–64 | **ACCUMULATE** | Solid, consider building a position |
| 35–49 | **HOLD** | Maintain current position |
| <35 | **AVOID** | Significant concerns |

### Dividend Tiers

| Tier | Consecutive Years | Badge |
|---|---|---|
| King | 50+ | 👑 |
| Aristocrat | 25–49 | 🏆 |
| Achiever | 10–24 | ⭐ |
| Contender | 5–9 | 📈 |
| Starter | <5 | 🌱 |

---

## Deploy to Google Cloud

> For full step-by-step instructions see [DEPLOY-GCP.md](DEPLOY-GCP.md).

### Recommended Instance

| Use case | Machine type | RAM | Cost (~24/7) |
|---|---|---|---|
| Personal / light use | `e2-small` | 2 GB | ~$14/month |
| **Recommended** | **`e2-medium`** | **4 GB** | **~$27/month** |
| Heavy analysis / many users | `e2-standard-2` | 8 GB | ~$53/month |

**`e2-medium` is the sweet spot** — it gives PostgreSQL, Streamlit, and the enrichment pipeline comfortable headroom without idle memory pressure. Use `e2-small` only for occasional personal use; it can run out of memory during bulk S&P 500 enrichment.

Use **30 GB** Balanced persistent disk and set a billing budget alert. Stop the VM when not in use to save credits.

### Summary Steps

```bash
# 1. Bootstrap the VM (one-time)
curl -fsSL https://raw.githubusercontent.com/blidiselalin/dividend-healthcheck/main/deploy/gcp/vm-bootstrap.sh | bash
# Log out and SSH back in, then:
cd ~/dividend-healthcheck

# 2. Configure environment
cp .env.example .env   # edit: POSTGRES_PASSWORD=...

# 3. Start the stack
docker compose up -d --build

# 4. Enable HTTPS (Caddy + Let's Encrypt)
sudo ./deploy/gcp/setup-https-caddy.sh

# 5. Build the market library
./scripts/update_cloud_docker.sh --ingest

# 6. Install hourly price refresh
./scripts/install_hourly_cron.sh

# 7. Update later
git pull && ./scripts/update_cloud_docker.sh
```

### GitHub Actions CI/CD

Set these repository **Variables**: `GCP_PROJECT_ID`, `GCP_INSTANCE`, `GCP_ZONE`  
Set this repository **Secret**: `GCP_SA_KEY` (service account JSON with SSH access)

Then trigger: **Actions → Deploy to GCP → Run workflow**.

---

## Troubleshooting

| Issue | Solution |
|---|---|
| `ModuleNotFoundError` | `pip install -r requirements.txt` |
| App shows no data | Check internet; yfinance requires network access |
| Sidebar shows `🌐 Public API` | Run `python ingest_data.py --ensure-sp500 --enrich-existing` |
| Slow analysis (API mode) | Normal (~0.2 s/request). Build the market library to speed up. |
| Container out of memory | Upgrade VM to `e2-medium` (4 GB RAM) |
| `container name already in use` | `docker rm -f dividendscope && docker compose up -d --build` |
| Port 8501 already in use | `streamlit run app.py --server.port 8502` |
| `streamlit: command not found` | `pip install streamlit` or `python -m streamlit run app.py` |
| HTTPS shows nginx page | Run `sudo ./deploy/gcp/setup-https-caddy.sh` on the VM |
| Empty market library after deploy | Run `./scripts/update_cloud_docker.sh --ingest` |
| PDF export fails | `pip install reportlab` (already in `requirements.txt`) |
| Login redirect mismatch | Add `https://your-domain/oauth2callback` to Google OAuth credentials |
| Tests fail with DB errors | Tests use SQLite — ensure `PYTEST_USE_SQLITE=1` is set (done automatically via `conftest.py`) |

---

**Disclaimer:** This tool is for educational purposes only. Not financial advice. Always do your own research and consult a qualified financial professional before investing.
