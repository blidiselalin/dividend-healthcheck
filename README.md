# 👑 DividendScope

**Intelligent financial analytics for dividend investors.**

Analyze elite Dividend Kings (50+ years of consecutive increases), assess dividend safety, track payout sustainability, and discover high-quality income opportunities — powered by a local vector database for fast, offline analysis.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/streamlit-1.30+-red.svg)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## What Are Dividend Kings?

**Dividend Kings** are companies that have raised their dividends for 50 or more consecutive years. This remarkable achievement requires:

- 📈 Consistent earnings through multiple economic cycles
- 💪 Conservative financial management
- 🛡️ Durable competitive advantages
- 👥 Shareholder-focused leadership

Only ~50 companies in the U.S. have achieved this elite status.

## Features

### Key Investor Metrics (Prime View)

The analyzer surfaces the **6 most important metrics** for dividend investors:

| Metric | Why It Matters |
|--------|----------------|
| **Dividend Streak** | Years of consecutive increases — the defining factor |
| **Dividend Yield** | Current income potential |
| **5Y Dividend Growth** | Historical CAGR indicates future growth |
| **Dividend Safety** | Payout ratio and coverage analysis |
| **Payout Ratio** | Sustainability of current dividend |
| **Income per $10K** | Actual annual income from investment |

### "Dividends Don't Lie" Philosophy

This analyzer implements the investment philosophy from Geraldine Weiss's classic 1988 book *Dividends Don't Lie*. The core principle: **a company's dividend policy is a more honest indicator of financial health than reported earnings.**

Why dividends don't lie:
- Dividends require **actual cash** — you can't fake cash flow
- Consistent dividend increases demonstrate **management confidence**
- Dividend history provides a **stable valuation anchor**
- High-quality dividend payers have **proven track records**

### Dividend Yield Channels Chart

Interactive 10-year yield channel visualization based on the "Dividends Don't Lie" methodology:

| Zone | Yield Level | Price Implication | Action |
|------|-------------|-------------------|--------|
| 🟢 Undervalued | Above historical avg | Price depressed | Consider buying |
| 🟡 Fair Value | Near historical avg | Fairly priced | Hold / DCA |
| 🔴 Overvalued | Below historical avg | Price elevated | Patience / Trim |

**Key Principles:**
- **Mean Reversion**: Yields tend to return to historical averages over time
- **Buy High Yield**: When yield is above average, price is typically below fair value
- **Sell Low Yield**: When yield is below average, price may be stretched
- **Dividend Growth Shifts Value**: Rising dividends push fair value price higher

### Sector Comparison with Reference Stocks

Compare your selected stock against:
1. **All dividend stocks in sector** from your analysis list
2. **Top 2-3 public reference stocks** — highly-rated dividend payers NOT in your list

Reference stocks are selected using dividend quality filters:
- Must have at least 3+ years consecutive dividend payments
- Yield between 0-10% (avoiding distress signals)
- Prioritized by dividend growth rate and payout sustainability

### Additional Analysis

- **Investment Thesis** — Automated strengths and concerns
- **Sector Comparison** — Rank against peers in the same sector
- **Valuation Metrics** — P/E, PEG, Price/Book, EV/EBITDA
- **Financial Health** — Debt levels, liquidity ratios
- **Performance** — 1Y/5Y returns, analyst targets

### Data Sources

Data aggregated from multiple public sources:
- **Market Data Aggregator** — Real-time quotes and fundamentals
- **Public Financial Filings** — SEC filings and company reports
- **Exchange Data** — Historical prices from Nasdaq
- **StockQuote.io** — Dividend history and streak data

## Installation

```bash
# Core dependencies
pip install yfinance pandas streamlit

# Optional: For vector database and semantic search
pip install chromadb

# Optional: For PDF report generation
pip install reportlab

# Optional: For automated data download
pip install requests beautifulsoup4

# Optional: For yield channel charts
pip install plotly
```

## Quick Start

### Web UI

```bash
streamlit run app.py
```

Open `http://localhost:8501` to access the analyzer.

### Automated Data Download

Download dividend data from public sources:

```bash
# Install download dependencies
pip install requests beautifulsoup4

# Download all data (Dividend Kings + Aristocrats)
python download_data.py

# Download from specific source
python download_data.py --source nasdaq --symbols KO JNJ PG

# Download and run ingestion automatically
python download_data.py --run-ingestion
```

### Data Ingestion

Build a local vector database from downloaded files:

```bash
# Create sample files to see expected format
python ingest_data.py --create-samples

# Run ingestion after downloading data
python ingest_data.py

# Search the database
python ingest_data.py --search "high yield consumer defensive"

# List all Dividend Kings
python ingest_data.py --list-kings
```

## Project Structure

```
dividend-king/
├── app.py                      # Streamlit entry point
├── config.py                   # Configuration (stock lists, thresholds)
├── download_data.py            # Automated data downloader
├── ingest_data.py              # Data ingestion CLI
├── models/
│   └── stock.py                # StockData model with dividend focus
├── services/
│   ├── stock_service.py        # Real-time data from APIs
│   ├── enhanced_stock_service.py  # Combined API + Vector DB
│   ├── scoring.py              # Dividend-focused scoring
│   ├── sector_service.py       # Sector comparison
│   └── report_generator.py     # PDF research report generation
├── ui/
│   ├── components.py           # Reusable UI components
│   └── views.py                # Page views (Single/Full analysis)
├── data_ingestion/             # Vector DB pipeline
│   ├── models.py               # StockDocument, DividendRecord
│   ├── downloaders.py          # StockQuote.io + Nasdaq parsers
│   ├── fetch_stockquote.py     # StockQuote.io automated fetcher
│   ├── fetch_nasdaq.py         # Nasdaq automated fetcher
│   ├── vector_store.py         # ChromaDB wrapper
│   └── pipeline.py             # Ingestion orchestration
├── data/
│   ├── downloads/              # Downloaded CSV/JSON files
│   │   ├── stockquote/         # StockQuote.io exports
│   │   └── nasdaq/             # Nasdaq historical data
│   └── vectordb/               # ChromaDB persistent storage
└── reports/                    # Generated CSV reports
```

## Data Download & Ingestion

### Automated Download

The `download_data.py` script fetches data automatically from public sources:

```bash
# Download everything (all Dividend Kings + Aristocrats)
python download_data.py

# Download specific symbols only
python download_data.py --symbols KO JNJ PG MMM

# Download from single source
python download_data.py --source nasdaq --symbols KO JNJ
python download_data.py --source stockquote

# Skip certain data types (faster)
python download_data.py --no-prices
python download_data.py --no-history

# Download and ingest in one step
python download_data.py --run-ingestion
```

Data is stored externally at `~/.dividendscope/data/`:
- `~/.dividendscope/data/downloads/` - Downloaded source files
- `~/.dividendscope/data/vectordb/` - Vector database

You can override the data location with the `DIVIDENDSCOPE_DATA_DIR` environment variable.

### Data Ingestion System

The data ingestion system allows you to build a local vector database from publicly available stock data. This enables:

- **Semantic search** — Find stocks by description (e.g., "high yield healthcare")
- **Enriched data** — Combine multiple sources for accuracy
- **Offline analysis** — Work without API calls
- **Historical tracking** — Store price and dividend history
- **UI Data Viewer** — Browse all stored data for any ticker in the app

### Vector Database Viewer

The UI includes a dedicated section to view all data stored in the vector database:

```python
from ui.components import UIComponents

# Display all vector DB data for a ticker
UIComponents.display_vector_db_data("KO")

# Display overall database statistics
UIComponents.display_vector_db_stats()
```

The viewer shows:
- **Basic Info** — Symbol, name, sector, industry, exchange
- **Dividend Metrics** — Yield, annual dividend, streak, payout ratio, tier
- **Price Data** — Current price, market cap, P/E ratio
- **Historical Data** — Price history and dividend payment records
- **Metadata** — Source, last updated, data quality score
- **Raw JSON** — Exportable data in JSON format

### Supported Data Sources

#### StockQuote.io

Download dividend data in CSV format:

| File | Contents |
|------|----------|
| `fundamentals.csv` | Symbol, Name, Sector, PE, Yield, Payout |
| `dividend_streaks.csv` | Symbol, ConsecutiveYears, Category |
| `dividend_history.csv` | Symbol, Ex-Date, Amount |

Expected format:
```csv
Symbol,Name,Sector,Industry,MarketCap,PE,DivYield,PayoutRatio
KO,Coca-Cola,Consumer Defensive,Beverages,265000000000,25.4,3.12,75.2
```

#### Nasdaq Historical

Download from Nasdaq historical pages:

| File | Contents |
|------|----------|
| `KO_historical.csv` | Date, Close, Volume, Open, High, Low |
| `KO_dividends.csv` | Ex-Date, Amount, Payment Date |

Expected format:
```csv
Date,Close/Last,Volume,Open,High,Low
03/14/2024,$60.12,12345678,$59.85,$60.45,$59.72
```

### CLI Commands

```bash
# Full ingestion from all sources
python ingest_data.py

# Process specific source
python ingest_data.py --source stockquote
python ingest_data.py --source nasdaq

# Process single file
python ingest_data.py --file data/downloads/stockquote/fundamentals.csv

# Search database
python ingest_data.py --search "technology dividend growth"

# List Dividend Kings
python ingest_data.py --list-kings

# Export/Import database
python ingest_data.py --export backup.json
python ingest_data.py --import backup.json

# Statistics
python ingest_data.py --stats
```

## Scoring Framework

The analyzer uses a dividend-focused scoring system (0-100):

| Factor | Weight | Description |
|--------|--------|-------------|
| Dividend Streak | 20% | Consecutive years of increases (50+ = max) |
| Dividend Safety | 15% | Payout ratio and coverage |
| Dividend Yield | 15% | Current yield (2.5-4.5% optimal) |
| Dividend Growth | 15% | 5-year CAGR of dividend increases |
| Valuation | 10% | P/E and price vs 52-week high |
| Financial Strength | 10% | Debt/Equity, current ratio |
| Profitability | 10% | ROE, profit margins |
| Size/Stability | 5% | Market cap (larger = more stable) |

### Recommendations

| Score | Label | Meaning |
|-------|-------|---------|
| 80+ | **STRONG BUY** | Excellent across all factors |
| 65-79 | **BUY** | Strong fundamentals, good value |
| 50-64 | **ACCUMULATE** | Solid, consider building position |
| 35-49 | **HOLD** | Maintain but don't add |
| <35 | **AVOID** | Significant concerns |

## Dividend Tiers

| Tier | Years | Badge |
|------|-------|-------|
| King | 50+ | 👑 |
| Aristocrat | 25-49 | 🏆 |
| Achiever | 10-24 | ⭐ |
| Contender | 5-9 | 📈 |
| Starter | <5 | 🌱 |

## Dividend Yield Channels

The analyzer implements the **"Dividends Don't Lie"** methodology by Geraldine Weiss (1988), one of the most respected dividend investing strategies.

### Core Principle

> *"A stock's dividend yield is the most honest indicator of its value."*
> — Geraldine Weiss

When a stock's yield is **high** relative to its historical norm, the stock is **undervalued**.  
When a stock's yield is **low** relative to its historical norm, the stock is **overvalued**.

### Valuation Zones

| Zone | Yield Percentile | Signal | Action |
|------|------------------|--------|--------|
| 💎 Deep Value | 90th+ | Exceptional opportunity | Strong Buy |
| 🟢 Value | 75th-90th | Good value | Buy |
| 🟡 Fair Value | 25th-75th | Fairly priced | Hold / DCA |
| 🟠 Caution | 10th-25th | Below average value | Wait |
| 🔴 Expensive | <10th | Price stretched | Avoid / Trim |

### Features

- **10-Year Historical Analysis**: Uses robust percentile-based zones
- **Price Targets**: Calculates exact prices at each yield level
- **Professional Charts**: Plotly-powered interactive visualizations
- **Weiss Interpretation**: Actionable buy/sell/hold signals
- **Vector DB Integration**: Uses stored dividend history when available

### Example Output

```
JNJ (Johnson & Johnson)
Zone: Expensive (Percentile: 8%)
Current Yield: 2.14%  |  Median: 3.07%

Price Targets:
  Deep Value: $153.98 (yield > 3.4%)
  Value:      $161.17 (yield > 3.2%)
  Fair Value: $169.65 (yield = 3.1%)
  Expensive:  $207.70 (yield < 2.5%)

Action: Avoid / Trim — Yield in bottom 10% historically.
```

### Best Practices from Top Investors

**Warren Buffett**:
> *"Price is what you pay, value is what you get."*

**Benjamin Graham**:
> *"The margin of safety is always dependent on the price paid."*

The yield channel strategy works best with:
- Blue-chip dividend growth stocks with 10+ year histories
- Companies with consistent, growing dividends
- Stable, mature businesses (utilities, consumer staples, healthcare)

## Configuration

Edit `config.py` to customize:

```python
# Stock lists
DIVIDEND_KINGS = [...]      # 50+ year streaks
DIVIDEND_ARISTOCRATS = [...] # 25+ year streaks

# Scoring thresholds
RECOMMENDATION_THRESHOLDS = {
    "strong_buy": 80,
    "buy": 65,
    "accumulate": 50,
    "hold": 35,
}

# API rate limiting
API_DELAY_SECONDS = 0.2
```

## UI Features

### Single Stock Analysis

1. Select from Dividend Kings or enter any symbol
2. View prime metrics at a glance
3. Read automated investment thesis
4. Compare with sector peers
5. Explore detailed metrics in expandable sections

### Full Analysis

1. Analyze all Dividend Kings (2-3 minutes)
2. View summary statistics
3. See top picks ranked by score
4. Filter by dividend streak and yield
5. Export results to CSV or PDF

### News Summary & Sentiment

Get the latest news and sentiment analysis from top financial sources:

```python
from services.news_service import NewsService

service = NewsService()
summary = service.fetch_news_summary("JNJ", days=7)

print(f"Sentiment: {summary.overall_sentiment}")
print(f"Score: {summary.sentiment_score}")
print(f"Articles: {summary.article_count}")
```

**Features:**
- Aggregates news from Yahoo Finance, Google News RSS
- Keyword-based sentiment analysis (bullish/bearish/neutral/mixed)
- Extracts key themes (earnings, dividend, growth, valuation, etc.)
- Highlights positive news and risk indicators
- No API keys required - uses public sources

**Sentiment Labels:**

| Label | Meaning | Emoji |
|-------|---------|-------|
| Bullish | More positive than negative news | 📈 |
| Bearish | More negative than positive news | 📉 |
| Mixed | Both positive and negative signals | 🔄 |
| Neutral | No strong sentiment detected | ➖ |

### PDF Research Reports

Generate professional research reports similar to analyst research documents:

```bash
# Install PDF generation dependency
pip install reportlab
```

Reports include:
- **Rate Card** - Score, yields, growth rates, key metrics
- **Dividend Analysis** - Growth rates, safety metrics, yield channels
- **Valuation** - P/E, price targets, financial strength ratings
- **Investment Thesis** - Automated strengths and concerns

Export directly from the UI after analyzing any stock.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Missing data | Some metrics unavailable for certain stocks |
| Slow analysis | Rate limiting prevents API blocks (0.2s/request) |
| Import errors | Run `pip install yfinance pandas streamlit` |
| ChromaDB errors | Optional; falls back to JSON storage |
| No vector data | Run `python download_data.py` then `python ingest_data.py` |
| Download rate limits | Scripts have built-in delays; run overnight if needed |
| Missing requests | Run `pip install requests beautifulsoup4` |
| PDF generation fails | Run `pip install reportlab` |
| News RSS fails | Run `pip install feedparser` (optional, Yahoo Finance works without it) |

---

**Disclaimer:** This tool is for educational purposes only. Not financial advice. Always do your own research and consult professionals before investing.
