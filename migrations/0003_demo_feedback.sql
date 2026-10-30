-- Auditable human review, independent of client-controlled request IDs.
BEGIN;
CREATE TABLE IF NOT EXISTS demo_review_sessions (
  request_id TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  token_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS demo_review_rows (
  request_id TEXT NOT NULL REFERENCES demo_review_sessions(request_id) ON DELETE CASCADE,
  item_index INTEGER NOT NULL CHECK (item_index >= 0),
  initial_status TEXT NOT NULL,
  initial_result JSONB NOT NULL,
  current_result JSONB NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0,
  decision TEXT NOT NULL DEFAULT 'PENDING',
  edited BOOLEAN NOT NULL DEFAULT FALSE,
  selected_ld_id BIGINT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (request_id, item_index)
);
CREATE TABLE IF NOT EXISTS demo_review_events (
  id BIGSERIAL PRIMARY KEY,
  request_id TEXT NOT NULL,
  item_index INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  event_data JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (request_id, item_index)
    REFERENCES demo_review_rows(request_id, item_index) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_demo_review_sessions_created
  ON demo_review_sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_demo_review_rows_decision
  ON demo_review_rows(decision);
CREATE INDEX IF NOT EXISTS idx_demo_review_events_created
  ON demo_review_events(created_at DESC);
COMMIT;
