-- DividendScope unified schema (Cloud SQL PostgreSQL)
-- Apply: python -m db.connection --migrate

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT,
  picture_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  is_admin BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS access_requests (
  email TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  name TEXT,
  picture_url TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  message TEXT,
  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewed_at TIMESTAMPTZ,
  reviewed_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_access_requests_status ON access_requests (status);

CREATE TABLE IF NOT EXISTS holdings (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  shares DOUBLE PRECISION NOT NULL,
  avg_cost_per_share DOUBLE PRECISION NOT NULL,
  acquisition_value DOUBLE PRECISION NOT NULL,
  commission DOUBLE PRECISION NOT NULL DEFAULT 0,
  dividends_paid DOUBLE PRECISION NOT NULL DEFAULT 0,
  estimated_avg_price DOUBLE PRECISION,
  sort_order INTEGER NOT NULL DEFAULT 0,
  company_name TEXT,
  PRIMARY KEY (user_id, symbol)
);

CREATE INDEX IF NOT EXISTS idx_holdings_user ON holdings (user_id);

CREATE TABLE IF NOT EXISTS purchase_journal (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  purchase_date DATE NOT NULL,
  price_usd DOUBLE PRECISION NOT NULL,
  UNIQUE (user_id, symbol, purchase_date, price_usd)
);

CREATE INDEX IF NOT EXISTS idx_purchase_journal_user ON purchase_journal (user_id);

CREATE TABLE IF NOT EXISTS monthly_deposits (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  period_key TEXT NOT NULL,
  year INTEGER NOT NULL,
  month INTEGER NOT NULL,
  label TEXT NOT NULL,
  deposit_eur DOUBLE PRECISION NOT NULL,
  deposit_usd DOUBLE PRECISION NOT NULL,
  portfolio_eur DOUBLE PRECISION NOT NULL,
  sort_order INTEGER NOT NULL,
  PRIMARY KEY (user_id, period_key)
);

CREATE TABLE IF NOT EXISTS net_dividends (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  period_key TEXT NOT NULL,
  year INTEGER NOT NULL,
  month INTEGER NOT NULL,
  net_usd DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (user_id, period_key)
);

-- Shared S&P / market library (all users)
CREATE TABLE IF NOT EXISTS stock_documents (
  symbol TEXT PRIMARY KEY,
  document JSONB NOT NULL,
  sector TEXT,
  dividend_streak_years INTEGER,
  dividend_yield DOUBLE PRECISION,
  data_quality DOUBLE PRECISION,
  last_updated TIMESTAMPTZ NOT NULL DEFAULT now(),
  source TEXT
);

CREATE INDEX IF NOT EXISTS idx_stock_documents_sector ON stock_documents (sector);
CREATE INDEX IF NOT EXISTS idx_stock_documents_streak ON stock_documents (dividend_streak_years);
CREATE INDEX IF NOT EXISTS idx_stock_documents_updated ON stock_documents (last_updated);

CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO schema_migrations (version)
VALUES ('001_initial')
ON CONFLICT (version) DO NOTHING;
