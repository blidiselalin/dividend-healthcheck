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
- [Quick Start — Docker (recommended)](#quick-start--docker-recommended)
- [Local Development (no Docker)](#local-development-no-docker)
- [Authentication](#authentication)
- [Portfolio Management](#portfolio-management)
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
| **Risk & Allocation** | Sector concentration, risk monitor, benchmark comparison |
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
| **Reverse proxy** | Caddy (host) | Auto-TLS via Let's Encrypt |

> **All portfolio data is user-scoped in PostgreSQL.** No SQLite or ChromaDB is used at runtime when `DATABASE_URL` is set.

## Architecture Guardrails

Use these conventions when extending the app so features remain fast, testable, and consistent:

- **One portfolio context per flow**: use `services.portfolio_context.create_portfolio_context()` for holdings + journal + dividends in the same request.
- **Service-first UI**: keep `ui/*` focused on rendering and state; move data orchestration and fallback logic to `services/*`.
- **Batch over per-symbol loops**: prefer `get_by_symbols()` / `load_documents()` style bulk fetches for holdings and screening views.
- **Cloud SQL as runtime source of truth**: when `DATABASE_URL` is set, avoid introducing new runtime SQLite/Chroma write paths.
- **Date parsing discipline**: parse DB values through `db.parsing` helpers to support both PostgreSQL and local SQLite tests.

---

## Quick Start — Docker (recommended)

Requires [Docker Desktop](https://docs.docker.com/get-docker/) (or Docker + Docker Compose on Linux).

**1. Clone the repository**

```bash
git clone https://github.com/blidiselalin/dividend-healthcheck.git
cd dividend-healthcheck
```

**2. Create the environment file**

```bash
cp .env.example .env
# Edit .env — change POSTGRES_PASSWORD before first run
```

**3. Start the app**

```bash
docker compose up -d --build
```

**4. Populate the market library** (first run only — takes ~15–20 minutes)

```bash
docker compose exec dividendscope python ingest_data.py --ensure-sp500 --enrich-existing
```

**5. Open the app**

Navigate to **http://localhost:8501**.

> The container entrypoint applies database migrations automatically on every start. You do not need to run migrations manually.

---

## Local Development (no Docker)

Use this path for running tests or iterating on code without a full Docker stack.

**Requirements:** Python 3.12, pip

```bash
git clone https://github.com/blidiselalin/dividend-healthcheck.git
cd dividend-healthcheck
pip install -r requirements.txt
streamlit run app.py
```

Without `DATABASE_URL` set, the app automatically falls back to ChromaDB (SQLite-backed) for the market library and local files for portfolios. This is fine for development but not recommended for production.

**Run tests**

```bash
python -m pytest tests/ -m "not integration"
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

Without secrets configured, the app renders a **Try as Demo User** button that loads a read-only sample portfolio — useful for evaluating the app before setting up OAuth.

---

## Portfolio Management

Once logged in, every user gets an isolated portfolio scoped to their account.

### Holdings & Purchase Journal

- Add holdings manually via the **Manage** panel or import from a CSV
- Each purchase is recorded in the journal with cost basis, quantity, and date
- The dashboard shows unrealized P&L, sector allocation, and market value

### Dividend Income

- **Monthly calendar** — upcoming ex-dates and estimated payments
- **Receipt log** — confirmed dividend payments with amounts
- **Growth chart** — income CAGR over time

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

# Database utilities
python ingest_data.py --stats                    # Show document counts
python ingest_data.py --list-kings               # List all Dividend Kings in library
python ingest_data.py --search "high yield tech" # Semantic search
python ingest_data.py --export backup.json       # Export library to JSON
python ingest_data.py --import backup.json       # Restore from JSON
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
├── auth/                           # Authentication (Google OAuth, user store, access requests)
│
├── db/                             # PostgreSQL layer
│   ├── connection.py               # Connection pool, schema migrations
│   ├── parsing.py                  # Date/type helpers for DB rows
│   ├── postgres_market_store.py    # Stock documents CRUD
│   └── postgres_market_history_store.py  # Price & dividend history tables
│
├── migrations/                     # Incremental SQL migration files
│   ├── 001_initial.sql
│   ├── 002_dividend_receipts.sql
│   └── 003_stock_market_history.sql
│
├── models/
│   └── stock.py                    # StockData and DividendHistory dataclasses
│
├── services/
│   ├── enhanced_stock_service.py   # DB-first, API-fallback orchestration
│   ├── portfolio_context.py        # Shared portfolio store factory
│   ├── portfolio_service.py        # Holdings, journal, deposits
│   ├── scoring.py                  # 0–100 dividend scoring engine
│   ├── news_service.py             # News aggregation and sentiment
│   ├── report_generator.py         # PDF report generation
│   ├── yield_channel_chart.py      # "Dividends Don't Lie" chart builder
│   ├── chatbot_service.py          # FAQ + optional Hugging Face assistant
│   ├── hourly_market_update.py     # Background price refresh
│   └── ...                         # Portfolio analytics (allocation, risk, income, benchmark)
│
├── data_ingestion/                 # Market library ingestion pipeline
│   ├── stock_enricher.py           # Yahoo + SEC EDGAR + Stooq enrichment
│   ├── providers/                  # Per-source adapters
│   ├── vector_store.py             # ChromaDB wrapper (dev/test fallback)
│   └── pipeline.py                 # CLI orchestration
│
├── ui/                             # Streamlit pages and components
│   ├── views.py                    # Single-stock and full-analysis pages
│   ├── portfolio_home.py           # Portfolio welcome and quick-actions
│   ├── portfolio_details_view.py   # Holdings, journal, income views
│   ├── admin_page.py               # Database admin and market library sync
│   ├── chatbot_widget.py           # Sidebar assistant widget
│   └── ...                         # Charts, risk panel, sidebar, theme
│
├── deploy/gcp/                     # GCP-specific scripts (bootstrap, Caddy, HTTPS)
├── scripts/                        # update_cloud_docker.sh, docker-entrypoint.sh
└── tests/                          # pytest suite (unit + integration)
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

# Optional
SEC_EDGAR_USER_AGENT=DividendScope/1.0 (you@yourdomain.com)
DIVIDENDSCOPE_CHATBOT_ENABLED=1
HUGGINGFACE_API_KEY=hf_...        # Server-side only — never expose to the browser
DIVIDENDSCOPE_CHATBOT_MODEL=facebook/blenderbot-400M-distill
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

### Deploy

```bash
# 1. Bootstrap Docker on a fresh Ubuntu 22.04 VM
curl -fsSL https://raw.githubusercontent.com/blidiselalin/dividend-healthcheck/main/deploy/gcp/vm-bootstrap.sh | bash
# Log out and back in so the docker group applies

# 2. Clone, configure, and start
git clone https://github.com/blidiselalin/dividend-healthcheck.git
cd dividend-healthcheck
cp .env.example .env   # edit POSTGRES_PASSWORD
docker compose up -d --build

# 3. Populate market library (first run)
docker compose exec dividendscope python ingest_data.py --ensure-sp500 --enrich-existing

# 4. Enable HTTPS (Caddy + Let's Encrypt — requires a domain pointed at the VM)
sudo ./deploy/gcp/setup-https-caddy.sh
```

### Update an existing deployment

```bash
cd ~/dividend-healthcheck
git pull
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
| `🌐 Public API (DB empty)` in sidebar | Run `python ingest_data.py --ensure-sp500 --enrich-existing` |
| Slow first-run ingestion | Normal — 15–20 min for full S&P 500 enrichment; market data is cached afterwards |
| `chromadb` import errors | `pip install chromadb>=0.4.22`; app works without it (API-only mode) |
| PDF export fails | `pip install reportlab` (included in `requirements.txt`) |
| News section empty | `pip install feedparser` (optional); Yahoo Finance news still works without it |
| Port 8501 already in use | `streamlit run app.py --server.port 8502` |
| `Server: nginx` on HTTPS domain | Run `sudo ./deploy/gcp/setup-https-caddy.sh` on VM (replaces nginx with Caddy) |
| Container name already in use | `docker rm -f dividendscope && docker compose up -d --build` |
| Out of memory on VM | Upgrade to e2-small (2 GB) or e2-medium (4 GB) |
| Google login redirect mismatch | Add the exact redirect URI to your Google OAuth 2.0 client and to `.streamlit/secrets.toml` |

---

**Disclaimer:** DividendScope is for educational and informational purposes only. It is not financial advice. Always conduct your own research and consult a qualified professional before making investment decisions.
