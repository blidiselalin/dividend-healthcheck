-- Persistent price history for benchmark ETFs/indexes used in portfolio comparison.
-- Data is shared across all users (no user_id scope), fetched from Yahoo Finance,
-- and refreshed on demand.  Separating from stock_price_history avoids a FK
-- dependency on stock_documents (benchmarks may not be S&P constituents).

CREATE TABLE IF NOT EXISTS benchmark_price_history (
  symbol      TEXT NOT NULL,
  price_date  DATE NOT NULL,
  close_usd   DOUBLE PRECISION NOT NULL,
  fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, price_date)
);

CREATE INDEX IF NOT EXISTS idx_benchmark_price_history_symbol_date
  ON benchmark_price_history (symbol, price_date DESC);

-- Descriptive metadata for each benchmark ETF/index used in comparison charts.
-- Populated once from a seed and updated via the admin UI / ingest pipeline.
CREATE TABLE IF NOT EXISTS benchmark_etf_info (
  symbol             TEXT PRIMARY KEY,
  display_name       TEXT NOT NULL,
  full_name          TEXT NOT NULL,
  description        TEXT,
  expense_ratio_pct  DOUBLE PRECISION,
  category           TEXT,
  currency           TEXT NOT NULL DEFAULT 'USD',
  best_practices     TEXT,
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO schema_migrations (version)
VALUES ('004_benchmark_price_history')
ON CONFLICT (version) DO NOTHING;
