-- Beta user feedback (global app database)

CREATE TABLE IF NOT EXISTS beta_feedback (
  id BIGSERIAL PRIMARY KEY,
  rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
  message TEXT NOT NULL,
  page TEXT NOT NULL,
  email TEXT,
  user_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_beta_feedback_created ON beta_feedback (created_at DESC);
