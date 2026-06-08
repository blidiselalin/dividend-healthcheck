-- Normalized price/dividend time series for yield charts and exposure tables.
-- Chroma stored these as price_history / dividend_history (and *_json metadata);
-- stock_documents keeps aggregated fundamentals; history lives here.

CREATE TABLE IF NOT EXISTS stock_price_history (
  symbol TEXT NOT NULL REFERENCES stock_documents (symbol) ON DELETE CASCADE,
  price_date DATE NOT NULL,
  open DOUBLE PRECISION,
  high DOUBLE PRECISION,
  low DOUBLE PRECISION,
  close DOUBLE PRECISION NOT NULL,
  adjusted_close DOUBLE PRECISION,
  volume BIGINT,
  PRIMARY KEY (symbol, price_date)
);

CREATE INDEX IF NOT EXISTS idx_stock_price_history_symbol_date
  ON stock_price_history (symbol, price_date DESC);

CREATE TABLE IF NOT EXISTS stock_dividend_history (
  symbol TEXT NOT NULL REFERENCES stock_documents (symbol) ON DELETE CASCADE,
  ex_date DATE NOT NULL,
  amount DOUBLE PRECISION NOT NULL,
  payment_date DATE,
  frequency TEXT,
  PRIMARY KEY (symbol, ex_date)
);

CREATE INDEX IF NOT EXISTS idx_stock_dividend_history_symbol_date
  ON stock_dividend_history (symbol, ex_date DESC);
