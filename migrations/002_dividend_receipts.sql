-- Per-user dividend cash received (auto-synced from market library + holdings)

CREATE TABLE IF NOT EXISTS dividend_receipts (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  ex_date DATE NOT NULL,
  pay_date DATE NOT NULL,
  per_share_usd DOUBLE PRECISION NOT NULL,
  shares_held DOUBLE PRECISION NOT NULL,
  gross_usd DOUBLE PRECISION NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, symbol, ex_date, per_share_usd)
);

CREATE INDEX IF NOT EXISTS idx_dividend_receipts_user ON dividend_receipts (user_id);
CREATE INDEX IF NOT EXISTS idx_dividend_receipts_user_symbol ON dividend_receipts (user_id, symbol);
CREATE INDEX IF NOT EXISTS idx_dividend_receipts_pay_date ON dividend_receipts (user_id, pay_date);

ALTER TABLE holdings ADD COLUMN IF NOT EXISTS dividend_tracking_since DATE;
