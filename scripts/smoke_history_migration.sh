#!/usr/bin/env bash
# Real PostgreSQL migration smoke; does not need LLM keys or product catalog.
set -euo pipefail

container="rag-history-smoke-$$"
cleanup() { docker rm -f "$container" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$container" \
  -e POSTGRES_PASSWORD=test-only-history-password \
  -e POSTGRES_DB=rag_tender postgres:16-alpine >/dev/null

for attempt in $(seq 1 60); do
  if docker exec "$container" pg_isready -U postgres -d rag_tender >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    echo "PostgreSQL did not become ready" >&2
    exit 1
  fi
  sleep 1
done

docker cp migrations/0001_request_history.sql "$container":/tmp/0001.sql
docker cp migrations/0002_request_history_surrogate_id.sql "$container":/tmp/0002.sql
docker exec "$container" psql -v ON_ERROR_STOP=1 -U postgres -d rag_tender -f /tmp/0001.sql >/dev/null

# Preserve a legacy row with a caller-supplied correlation ID.
docker exec -i "$container" psql -v ON_ERROR_STOP=1 -U postgres -d rag_tender >/dev/null <<'SQL'
INSERT INTO rag_match_requests (
    request_id, created_at, completed_at, status, http_status,
    product_count, matched_count, latency_ms,
    request_json, response_json
) VALUES (
    'same-client-request-id', now(), now(), 'OK', 200,
    1, 0, 2.0,
    '{"products":["original"]}'::jsonb,
    '{"results":[{"input":"original","status":"NOT_FOUND"}]}'::jsonb
);
SQL

docker exec "$container" psql -v ON_ERROR_STOP=1 -U postgres -d rag_tender -f /tmp/0002.sql >/dev/null

# After upgrade the same X-Request-ID may be used by a second operation.
docker exec -i "$container" psql -v ON_ERROR_STOP=1 -U postgres -d rag_tender >/dev/null <<'SQL'
INSERT INTO rag_match_requests (
    request_id, created_at, completed_at, status, http_status,
    product_count, matched_count, latency_ms,
    request_json, response_json
) VALUES (
    'same-client-request-id', now(), now(), 'OK', 200,
    1, 1, 3.0,
    '{"products":["updated"]}'::jsonb,
    '{"results":[{"input":"updated","status":"MATCHED"}]}'::jsonb
);

DO $check$
BEGIN
    IF (SELECT COUNT(*) FROM rag_match_requests WHERE request_id = 'same-client-request-id') <> 2 THEN
        RAISE EXCEPTION 'Two request snapshots must survive independently';
    END IF;
    IF (SELECT COUNT(DISTINCT history_id) FROM rag_match_requests
        WHERE request_id = 'same-client-request-id') <> 2 THEN
        RAISE EXCEPTION 'Each stored snapshot needs a unique history_id';
    END IF;
    IF (SELECT COUNT(DISTINCT request_json->'products'->>0) FROM rag_match_requests
        WHERE request_id = 'same-client-request-id') <> 2 THEN
        RAISE EXCEPTION 'Legacy or new request payload overwritten';
    END IF;
    IF (SELECT COUNT(DISTINCT response_json->'results'->0->>'input') FROM rag_match_requests
        WHERE request_id = 'same-client-request-id') <> 2 THEN
        RAISE EXCEPTION 'Legacy or new response payload overwritten';
    END IF;
    IF (SELECT COUNT(DISTINCT history_id) FROM rag_match_items
        WHERE request_id = 'same-client-request-id') <> 2 THEN
        RAISE EXCEPTION 'Item view must identify both snapshots';
    END IF;
END;
$check$;
SQL

# Rerunning after an interrupted version-marker write is safe.
docker exec "$container" psql -v ON_ERROR_STOP=1 -U postgres -d rag_tender -f /tmp/0002.sql >/dev/null

echo "PASS: migration preserves legacy snapshot and accepts duplicate X-Request-ID."
