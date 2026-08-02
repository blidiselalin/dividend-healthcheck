-- Dividend receipt provenance, deduplication, and classification for broker imports.

ALTER TABLE dividend_receipts
  ADD COLUMN IF NOT EXISTS broker_account TEXT;

ALTER TABLE dividend_receipts
  ADD COLUMN IF NOT EXISTS broker_transaction_id TEXT;

ALTER TABLE dividend_receipts
  ADD COLUMN IF NOT EXISTS source_file_hash TEXT;

ALTER TABLE dividend_receipts
  ADD COLUMN IF NOT EXISTS source_row_number INTEGER;

ALTER TABLE dividend_receipts
  ADD COLUMN IF NOT EXISTS dedup_key TEXT;

ALTER TABLE dividend_receipts
  ADD COLUMN IF NOT EXISTS transaction_status TEXT NOT NULL DEFAULT 'posted';

ALTER TABLE dividend_receipts
  ADD COLUMN IF NOT EXISTS dividend_type TEXT NOT NULL DEFAULT 'actual';

ALTER TABLE dividend_receipts
  ADD COLUMN IF NOT EXISTS withholding_usd DOUBLE PRECISION NOT NULL DEFAULT 0;

ALTER TABLE dividend_receipts
  ADD COLUMN IF NOT EXISTS net_usd DOUBLE PRECISION;

ALTER TABLE dividend_receipts
  ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'USD';

ALTER TABLE dividend_receipts
  ADD COLUMN IF NOT EXISTS is_excluded BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE dividend_receipts
  ADD COLUMN IF NOT EXISTS exclusion_reason TEXT;

ALTER TABLE dividend_receipts
  ADD COLUMN IF NOT EXISTS description TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_dividend_receipts_dedup_unique
  ON dividend_receipts (user_id, dedup_key)
  WHERE dedup_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_dividend_receipts_posted_totals
  ON dividend_receipts (user_id, pay_date)
  WHERE is_excluded = FALSE
    AND transaction_status = 'posted'
    AND dividend_type IN ('actual', 'payment_in_lieu');

INSERT INTO schema_migrations (version)
VALUES ('011_dividend_receipt_provenance')
ON CONFLICT (version) DO NOTHING;
