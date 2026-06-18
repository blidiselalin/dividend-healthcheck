-- Add dividend_tracking_since to holdings (was present in SQLite schema but missing from 001_initial.sql).
-- Add composite index on purchase_journal(user_id, symbol) for faster per-symbol journal lookups.

ALTER TABLE holdings
  ADD COLUMN IF NOT EXISTS dividend_tracking_since TEXT;

CREATE INDEX IF NOT EXISTS idx_purchase_journal_user_symbol
  ON purchase_journal (user_id, symbol);

INSERT INTO schema_migrations (version)
VALUES ('005_holdings_tracking_since_and_indexes')
ON CONFLICT (version) DO NOTHING;
