-- Per-lot share count and commission on purchase journal entries.

ALTER TABLE purchase_journal
  ADD COLUMN IF NOT EXISTS shares DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS commission_usd DOUBLE PRECISION NOT NULL DEFAULT 0;

INSERT INTO schema_migrations (version)
VALUES ('008_purchase_journal_shares_commission')
ON CONFLICT (version) DO NOTHING;
