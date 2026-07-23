-- Allow IBKR dividend corrections/reversals on the same ex-date and per-share rate.

ALTER TABLE dividend_receipts
  DROP CONSTRAINT IF EXISTS dividend_receipts_user_id_symbol_ex_date_per_share_usd_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_dividend_receipts_event_unique
  ON dividend_receipts (user_id, symbol, ex_date, per_share_usd, gross_usd);

INSERT INTO schema_migrations (version)
VALUES ('010_dividend_receipt_gross_unique')
ON CONFLICT (version) DO NOTHING;
