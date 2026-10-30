-- Request IDs supplied by callers are correlation labels, NOT unique events.
-- Preserve legacy snapshots while allowing arbitrarily many responses with the
-- same X-Request-ID. PostgreSQL 16 supplies gen_random_uuid() natively.
BEGIN;

ALTER TABLE public.rag_match_requests
    ADD COLUMN IF NOT EXISTS history_id UUID;

UPDATE public.rag_match_requests
SET history_id = gen_random_uuid()
WHERE history_id IS NULL;

ALTER TABLE public.rag_match_requests
    ALTER COLUMN history_id SET DEFAULT gen_random_uuid(),
    ALTER COLUMN history_id SET NOT NULL;

-- Legacy and freshly provisioned databases can use different PK names.
-- Drop only the existing PK, preserving other indexes / business views.
DO $$
DECLARE
    old_primary_key TEXT;
BEGIN
    SELECT con.conname INTO old_primary_key
    FROM pg_constraint AS con
    WHERE con.conrelid = 'public.rag_match_requests'::regclass
      AND con.contype = 'p';

    IF old_primary_key IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE public.rag_match_requests DROP CONSTRAINT %I',
            old_primary_key
        );
    END IF;
END;
$$;

ALTER TABLE public.rag_match_requests
    ADD CONSTRAINT rag_match_requests_pkey PRIMARY KEY (history_id);

CREATE INDEX IF NOT EXISTS idx_rag_match_requests_correlation_history
    ON public.rag_match_requests (request_id, created_at DESC);

-- Postgres CREATE OR REPLACE VIEW allows appending columns without changing
-- legacy column order. Each item can now be attributed to its unique snapshot.
CREATE OR REPLACE VIEW public.rag_match_items AS
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
    item.value->>'error_code' AS error_code,
    r.history_id
FROM public.rag_match_requests AS r
CROSS JOIN LATERAL
    jsonb_array_elements(
        COALESCE(r.response_json->'results', '[]'::jsonb)
    ) WITH ORDINALITY AS item(value, ordinality);

COMMIT;
