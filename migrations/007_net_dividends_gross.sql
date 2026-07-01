-- Store synced gross dividend cash alongside net monthly totals

ALTER TABLE net_dividends ADD COLUMN IF NOT EXISTS gross_usd DOUBLE PRECISION;

INSERT INTO schema_migrations (version)
VALUES ('007_net_dividends_gross')
ON CONFLICT (version) DO NOTHING;
