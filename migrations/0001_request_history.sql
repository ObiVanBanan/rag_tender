BEGIN;

CREATE TABLE IF NOT EXISTS rag_match_requests (
    request_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    http_status INTEGER NOT NULL,
    product_count INTEGER NOT NULL,
    matched_count INTEGER NOT NULL,
    latency_ms DOUBLE PRECISION NOT NULL,
    request_json JSONB NOT NULL,
    response_json JSONB NOT NULL,
    error TEXT
);

DROP VIEW IF EXISTS rag_match_items;

ALTER TABLE rag_match_requests
    ALTER COLUMN request_id TYPE TEXT
    USING request_id::text;

CREATE INDEX IF NOT EXISTS idx_rag_match_requests_created_at
    ON rag_match_requests (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rag_match_requests_status
    ON rag_match_requests (status);

CREATE OR REPLACE VIEW rag_match_items AS
SELECT
    r.request_id,
    r.created_at,
    r.completed_at,
    r.status AS request_status,
    r.latency_ms AS request_latency_ms,
    item.ordinality::INTEGER AS item_index,
    item.value->>'input' AS input,
    item.value->>'status' AS item_status,
    item.value->>'matched_name' AS matched_name,
    item.value->>'matched_article' AS matched_article,
    NULLIF(item.value->>'score', '')::DOUBLE PRECISION AS score,
    NULLIF(item.value->>'confidence', '')::DOUBLE PRECISION AS confidence,
    item.value->>'error_code' AS error_code
FROM rag_match_requests AS r
CROSS JOIN LATERAL
    jsonb_array_elements(
        COALESCE(r.response_json->'results', '[]'::jsonb)
    ) WITH ORDINALITY AS item(value, ordinality);

COMMIT;
