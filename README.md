# 👑 DividendScope

**Intelligent financial analytics for dividend investors.**

Analyze elite Dividend Kings (50+ years of consecutive increases), assess dividend safety, track payout sustainability, and discover high-quality income opportunities — powered by a local vector database for fast, offline analysis.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/streamlit-1.30+-red.svg)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start — UI in 3 Steps](#quick-start--ui-in-3-steps)
- [Full Setup — With Local Vector Database](#full-setup--with-local-vector-database)
- [Using the UI](#using-the-ui)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Market data sources](#market-data-sources)
- [Features Reference](#features-reference)
- [Data Download & Ingestion CLI](#data-download--ingestion-cli)
- [Scoring Framework](#scoring-framework)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| **Python** | 3.10 or higher | [Download](https://www.python.org/downloads/) |
| **pip** | Latest recommended | Comes with Python |
| Internet access | — | Required for live market data (Yahoo / optional APIs) |

> **No API keys required.** Market data uses Yahoo Finance, SEC EDGAR, and Stooq — all free public sources.

---

## Quick Start — UI in 3 Steps

The fastest way to get the app running. Uses live public API data with no local database setup required.

**Step 1 — Clone and enter the project**

```bash
git clone https://github.com/blidiselalin/dividend-healthcheck.git
cd dividend-healthcheck
```

**Step 2 — Install dependencies**

```bash
pip install -r requirements.txt
```

**Step 3 — Launch the UI**

```bash
streamlit run app.py
```

Open **http://localhost:8501** in your browser. The app is ready to use.

> **Tip:** On first launch the sidebar shows `🌐 Public API`. This is normal — it means the app is fetching live data directly from the market. Analysis may take a few seconds per stock due to API rate limiting.

---

## Full Setup — With Local Vector Database

For faster analysis, offline use, and enriched historical data, populate the local vector database. This is optional but highly recommended for the full experience.

**Step 1 — Download public stock data**

```bash
python download_data.py
```

This fetches Dividend Kings and Aristocrats data from public sources into `~/.dividendscope/data/downloads/`. The script has built-in rate limiting — expect 5–15 minutes for a full download.

**Step 2 — Ingest data into the vector database**

```bash
python ingest_data.py --enrich
```

The `--enrich` flag also pulls live fundamentals (P/E, payout ratio, etc.) from yfinance for each stock. This takes 10–20 minutes for the full list.

**Step 3 — Launch the UI**

```bash
streamlit run app.py
```

Once the vector database is populated, the sidebar shows `🗄️ Vector DB (N stocks)`. All analysis now runs from local data — no API calls for the core metrics.

### Environment Variable Override

By default, data is stored at `~/.dividendscope/data/`. Override with:

```bash
export DIVIDENDSCOPE_DATA_DIR=/your/custom/path
streamlit run app.py
```

---

## Using the UI

### Sidebar

| Element | Description |
|---|---|
| **Analysis Mode** | Switch between Single Stock and All Dividend Kings |
| **Data Source** | Shows whether DB or live API is active |

### Single Stock Analysis

1. Select a ticker from the Dividend Kings dropdown, or type any symbol in the text box
2. Click **Analyze** to load data
3. The **Prime Metrics** panel shows the 6 most important dividend figures at a glance
4. Scroll down for the **Investment Thesis**, **Sector Comparison**, **Yield Channels** chart, and detailed metric tables
5. Expand the **News & Sentiment** section for recent headlines and sentiment score
6. Click **Download PDF Report** to export a professional research report

### All Dividend Kings Analysis

1. Select **All Dividend Kings** in the sidebar
2. Click **Run Full Analysis** — this analyzes all stocks in the list (~2–3 minutes via API, ~30 seconds with DB)
3. Use the **Filters** to narrow by minimum dividend streak and yield range
4. The results table is sortable; click any column header to re-rank
5. Use **Export CSV** or **Export PDF** to save results

### Data Source Status

| Sidebar indicator | Meaning |
|---|---|
| `🗄️ Vector DB (N stocks)` | Local database active — fast, offline-capable |
| `🌐 Public API (DB empty)` | Live API mode — populate DB with `python ingest_data.py --enrich` |
| `🌐 Public API only` | chromadb not installed — install it to enable the local database |

---

## Project Structure

```
dividend-healthcheck/
├── app.py                         # Streamlit entry point
├── config.py                      # Stock lists, scoring weights, thresholds
├── download_data.py               # Automated public data downloader
├── ingest_data.py                 # Vector database ingestion CLI
├── requirements.txt               # All Python dependencies
│
├── models/
│   └── stock.py                   # StockData and DividendHistory dataclasses
│
├── services/
│   ├── stock_service.py           # Live data from yfinance
│   ├── enhanced_stock_service.py  # DB-first, API fallback orchestration
│   ├── vectordb_service.py        # Read-only vector DB service for the UI
│   ├── scoring.py                 # Dividend-focused 0–100 scoring engine
│   ├── sector_service.py          # Sector peer comparison
│   ├── news_service.py            # News aggregation and sentiment analysis
│   ├── report_generator.py        # PDF research report generation
│   └── yield_channel_chart.py     # "Dividends Don't Lie" chart builder
│
├── ui/
│   ├── components.py              # Reusable Streamlit UI components
│   └── views.py                   # Page views (Single Stock / Full Analysis)
│
├── data_ingestion/                # Vector database pipeline
│   ├── models.py                  # StockDocument, DividendRecord schemas
│   ├── stock_enricher.py          # Multi-source enrich entry (Yahoo + SEC + Stooq)
│   ├── providers/                 # Yahoo, SEC EDGAR, Stooq adapters + StockSnapshot
│   ├── downloaders.py             # StockQuote.io + Nasdaq CSV parsers
│   ├── fetch_stockquote.py        # StockQuote.io automated fetcher
│   ├── fetch_nasdaq.py            # Nasdaq historical data fetcher
│   ├── yfinance_enricher.py       # Legacy yfinance post-processing (streaks, CAGR)
│   ├── vector_store.py            # ChromaDB wrapper (search, get, upsert)
│   └── pipeline.py                # Ingestion orchestration and CLI logic
│
└── tests/
    └── test_data_accuracy.py      # Data accuracy tests
```

**Data stored outside the repo** (never committed):

```
~/.dividendscope/data/
├── downloads/
│   ├── stockquote/                # StockQuote.io CSV exports
│   └── nasdaq/                    # Nasdaq historical CSVs
└── vectordb/                      # ChromaDB persistent storage
```

---

## Configuration

All tunable parameters live in `config.py`. No environment variables needed for basic use.

```python
# Stock universe — edit to add/remove tickers
DIVIDEND_KINGS = ["KO", "JNJ", "PG", ...]      # 50+ year streak stocks
DIVIDEND_ARISTOCRATS = ["ABBV", "ADM", ...]     # 25+ year streak stocks

# Scoring thresholds
RECOMMENDATION_THRESHOLDS = {
    "strong_buy": 80,
    "buy": 65,
    "accumulate": 50,
    "hold": 35,
}

# API rate limiting (increase if hitting limits)
API_DELAY_SECONDS = 0.2
API_TIMEOUT_SECONDS = 30

# Data freshness — how many days before re-fetching from API
DEFAULT_STALENESS_DAYS = 7
```

---

## Market data sources

Enrichment runs through `data_ingestion/stock_enricher.py` in priority order:

| Source | API key? | Fills gaps in |
|--------|----------|----------------|
| **Yahoo Finance** (yfinance) | No | Price, dividends, fundamentals, history |
| **SEC EDGAR** | No | Company name, sector (SIC), margins, ROE, debt/equity from filings |
| **Stooq** | No | Daily OHLCV history and 52-week range when Yahoo history fails |

Providers only fill **missing** fields; nothing is overwritten.

SEC requests require a descriptive `User-Agent` header (SEC policy, not a secret). Default is built in; override for production:

```bash
export SEC_EDGAR_USER_AGENT="DividendScope/1.0 (you@yourdomain.com)"
```

Check active providers:

```python
from data_ingestion.stock_enricher import provider_status
print(provider_status())
```

---

## Features Reference

### What Are Dividend Kings?

**Dividend Kings** are companies that have raised their dividends for **50 or more consecutive years**. This requires:

- 📈 Consistent earnings through multiple economic cycles
- 💪 Conservative financial management
- 🛡️ Durable competitive advantages
- 👥 Shareholder-focused leadership

Only ~50 companies in the U.S. have achieved this elite status.

### Dividend Tiers

| Tier | Consecutive Years | Badge |
|---|---|---|
| King | 50+ | 👑 |
| Aristocrat | 25–49 | 🏆 |
| Achiever | 10–24 | ⭐ |
| Contender | 5–9 | 📈 |
| Starter | <5 | 🌱 |

### Key Investor Metrics (Prime View)

| Metric | Why It Matters |
|---|---|
| **Dividend Streak** | Years of consecutive increases — the defining factor |
| **Dividend Yield** | Current income potential |
| **5Y Dividend Growth** | CAGR of dividend increases |
| **Dividend Safety** | Payout ratio and coverage analysis |
| **Payout Ratio** | Sustainability of current dividend |
| **Income per $10K** | Actual annual income from a $10,000 investment |

### Dividend Yield Channels ("Dividends Don't Lie")

Based on Geraldine Weiss's 1988 methodology: a stock's dividend yield is its most honest valuation signal.

| Zone | Yield Percentile | Signal | Action |
|---|---|---|---|
| 💎 Deep Value | 90th+ | Exceptional opportunity | Strong Buy |
| 🟢 Value | 75th–90th | Good value | Buy |
| 🟡 Fair Value | 25th–75th | Fairly priced | Hold / DCA |
| 🟠 Caution | 10th–25th | Below average value | Wait |
| 🔴 Expensive | <10th | Price stretched | Avoid / Trim |

### News & Sentiment

Aggregates headlines from Yahoo Finance and Google News RSS. No API key required.

| Label | Meaning |
|---|---|
| 📈 Bullish | More positive than negative signals |
| 📉 Bearish | More negative than positive signals |
| 🔄 Mixed | Both positive and negative present |
| ➖ Neutral | No strong signal detected |

### PDF Research Reports

Install `reportlab` (included in `requirements.txt`) then export from the UI. Reports include score card, dividend analysis, valuation metrics, and automated investment thesis.

---

## Data Download & Ingestion CLI

### Download Commands

```bash
# Download all data (Dividend Kings + Aristocrats)
python download_data.py

# Download specific symbols only
python download_data.py --symbols KO JNJ PG MMM

# Download from a single source
python download_data.py --source nasdaq
python download_data.py --source stockquote

# Skip price history (faster)
python download_data.py --no-prices --no-history

# Download and ingest in one command
python download_data.py --run-ingestion
```

### Ingestion Commands

```bash
# Full ingestion (parse downloaded files into vector DB)
python ingest_data.py

# Ingest and enrich with live yfinance data (recommended)
python ingest_data.py --enrich

# Process a single source
python ingest_data.py --source stockquote
python ingest_data.py --source nasdaq

# Process one file
python ingest_data.py --file path/to/fundamentals.csv

# Enrich stocks already in the database
python ingest_data.py --enrich-existing
python ingest_data.py --enrich-existing --symbols KO,JNJ,PG

# Database utilities
python ingest_data.py --stats                    # Show document counts
python ingest_data.py --list-kings               # List all Dividend Kings
python ingest_data.py --search "high yield tech" # Semantic search
python ingest_data.py --consolidate              # Remove duplicates
python ingest_data.py --fix-values              # Fix invalid data
python ingest_data.py --export backup.json      # Export to JSON
python ingest_data.py --import backup.json      # Import from JSON
python ingest_data.py --clear                   # Wipe the database

# Create sample CSV files (to see expected input format)
python ingest_data.py --create-samples
```

### Expected CSV Formats

**StockQuote fundamentals (`fundamentals.csv`)**
```csv
Symbol,Name,Sector,Industry,MarketCap,PE,DivYield,PayoutRatio
KO,Coca-Cola,Consumer Defensive,Beverages,265000000000,25.4,3.12,75.2
```

**Nasdaq historical (`KO_historical.csv`)**
```csv
Date,Close/Last,Volume,Open,High,Low
03/14/2024,$60.12,12345678,$59.85,$60.45,$59.72
```

---

## Scoring Framework

| Factor | Weight | Description |
|---|---|---|
| Dividend Streak | 20% | Consecutive years of increases (50+ = max score) |
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

---

## Troubleshooting

| Issue | Solution |
|---|---|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| App opens but shows no data | Check internet connection; yfinance requires network access |
| Slow single-stock analysis | Normal — API rate limiting adds ~0.2 s/request. Use vector DB to speed up. |
| Slow full analysis (API mode) | Expected (~2–3 min for 50+ stocks). Run `python ingest_data.py --enrich` to build the DB. |
| Sidebar shows `🌐 Public API (DB empty)` | Run `python download_data.py && python ingest_data.py --enrich` |
| `chromadb` import errors | Run `pip install chromadb>=0.4.22`; the app works without it (API-only mode) |
| Download rate limits / timeouts | Built-in delays handle most cases; try `--symbols` to download a smaller batch |
| PDF export fails | Run `pip install reportlab` |
| News section empty | Run `pip install feedparser` (optional); Yahoo Finance news still works without it |
| `streamlit: command not found` | Run `pip install streamlit` or use `python -m streamlit run app.py` |
| Port 8501 already in use | Run `streamlit run app.py --server.port 8502` |

---

**Disclaimer:** This tool is for educational purposes only. Not financial advice. Always do your own research and consult a qualified professional before investing.
