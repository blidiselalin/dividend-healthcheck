-- Standard unique index for dividend dedup keys (works without partial ON CONFLICT).

UPDATE dividend_receipts
SET dedup_key = NULL
WHERE dedup_key = '';

UPDATE dividend_receipts
SET dedup_key = NULL
WHERE is_excluded = TRUE
  AND dedup_key IS NOT NULL;

WITH ranked AS (
  SELECT
    id,
    ROW_NUMBER() OVER (
      PARTITION BY user_id, dedup_key ORDER BY id
    ) AS rn
  FROM dividend_receipts
  WHERE dedup_key IS NOT NULL
    AND COALESCE(is_excluded, FALSE) = FALSE
)
UPDATE dividend_receipts dr
SET is_excluded = TRUE,
    exclusion_reason = 'duplicate_dedup_key',
    dedup_key = NULL
FROM ranked r
WHERE dr.id = r.id
  AND r.rn > 1;

DROP INDEX IF EXISTS idx_dividend_receipts_dedup_unique;

CREATE UNIQUE INDEX idx_dividend_receipts_dedup_unique
  ON dividend_receipts (user_id, dedup_key);

INSERT INTO schema_migrations (version)
VALUES ('012_dividend_receipt_dedup_unique')
ON CONFLICT (version) DO NOTHING;
