-- Broker import metadata: lot side/source and receipt source.

ALTER TABLE purchase_journal
  ADD COLUMN IF NOT EXISTS side TEXT NOT NULL DEFAULT 'buy';

ALTER TABLE purchase_journal
  ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual';

ALTER TABLE dividend_receipts
  ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'computed';

-- Allow buy and sell on same symbol/date/price.
ALTER TABLE purchase_journal
  DROP CONSTRAINT IF EXISTS purchase_journal_user_id_symbol_purchase_date_price_usd_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_purchase_journal_lot_unique
  ON purchase_journal (user_id, symbol, purchase_date, price_usd, side);

INSERT INTO schema_migrations (version)
VALUES ('009_broker_import_metadata')
ON CONFLICT (version) DO NOTHING;
