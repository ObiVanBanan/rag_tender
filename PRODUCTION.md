# Production API

This branch wraps the matcher in a production-oriented HTTP service. It adds a review-only candidate shortlist and explicit gas/liquid medium policy while preserving the existing `/v1/match` response contract.

## Runtime

- FastAPI: HTTP API and OpenAPI docs.
- Qdrant: champion dense index.
- PostgreSQL: full request/response history.
- Existing matcher: hybrid dense + BM25 + RRF + DeepSeek query interpretation/reranking.
- Optional DuckDuckGo MCP enrichment remains enabled exactly as configured by the champion.
- Grafana/Prometheus are intentionally deferred to backlog issue #4.

The API runs with one Uvicorn worker by default because the product catalog and BM25 index are kept in memory. Increasing workers duplicates that memory.

The production image installs Python dependencies from `uv.lock` with `uv sync --locked`. Update dependencies by reviewing `pyproject.toml`, regenerating `uv.lock`, running the test suite, and rebuilding the image. The DuckDuckGo MCP executable is installed from that same lock; `WEB_SEARCH_MCP_COMMAND=uvx` remains supported for deployments that intentionally prefer the legacy ephemeral runner.

PostgreSQL and the API publish host ports on `127.0.0.1` by default. Qdrant has no published host port and is reachable only on the Compose backend network. Remote API access should go through a TLS-terminating reverse proxy.
Compose generates project-scoped container names to avoid collisions with
other deployments. Services use Compose DNS names (`qdrant`, `postgres`) for
internal traffic and stable network aliases for the shared observability
network.
The API container runs as UID 10001 with a read-only root filesystem, a bounded
temporary filesystem, all Linux capabilities dropped, and privilege escalation
disabled. Its competitor knowledge database is stored on the dedicated writable
`competitor_kb` volume. Before API startup, a one-shot isolated init container
assigns that volume to UID 10001; it has only the `CHOWN` capability, no network,
and does not read or modify database contents.

## First start

The Qdrant snapshot is stored through Git LFS. Make sure it is materialized before Docker starts:

```powershell
git lfs install
git lfs pull
Copy-Item .env.example .env
```

Set at least these values in `.env`:

```text
OPENAI_API_KEY=...
DEEPSEEK_API_KEY=...
POSTGRES_PASSWORD=<unique random password>
API_DATABASE_USER=rag_tender_api
API_DATABASE_PASSWORD=<unique random password>
API_AUTH_TOKEN=<unique random bearer token, at least 32 characters>
```

Generate high-entropy values locally, for example with
`python -c "import secrets; print(secrets.token_urlsafe(48))"`; generate a distinct value for each secret. The API refuses
to start in production without a sufficiently long `API_AUTH_TOKEN`. The normal
Compose profile publishes the API only on `127.0.0.1`; put a TLS reverse proxy
in front of it for remote access. `/health/live` and `/health/ready` remain
unauthenticated for container health checks. The docs and OpenAPI schema are
public and declare bearer auth for operational routes; matching and metrics
require `Authorization: Bearer <API_AUTH_TOKEN>`.

`POSTGRES_USER` and `POSTGRES_PASSWORD` are reserved for the database
administration and migration job. Compose provisions `API_DATABASE_USER` as a
separate non-superuser role; each migration run resets its role memberships and
public-schema grants to an allowlist. The API can connect, read the schema
migration version, and insert request-history records, but cannot create or
alter schema. Keep `API_DATABASE_USER` distinct from `POSTGRES_USER`.

Then start the stack:

```powershell
docker compose up -d --build
docker compose ps
```

The `qdrant-init` one-shot container restores `qdrant/steel_products_active.snapshot` only when the collection does not already exist. It fails with a clear message if the snapshot is still a Git LFS pointer. The `db-migrate` one-shot container applies versioned SQL migrations before the API starts. The API checks the migration state and never changes the database schema itself.
The `competitor-kb-init` one-shot container normalizes ownership on the existing
knowledge volume before API startup so the non-root API can update its SQLite
database. It is isolated from the network and receives only `CAP_CHOWN`.

## Health and docs

```powershell
Invoke-RestMethod http://localhost:8000/health/live
Invoke-RestMethod http://localhost:8000/health/ready
```

Swagger UI:

```text
http://localhost:8000/docs
```

## Match API

Request:

```json
{
  "products": [
    "Кран шаровой муфтовый Ду25",
    "Задвижка неизвестного типа XYZ"
  ]
}
```

PowerShell:

```powershell
$body = @{
  products = @(
    "Кран шаровой муфтовый Ду25",
    "Задвижка неизвестного типа XYZ"
  )
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/v1/match `
  -Headers @{ Authorization = "Bearer $env:API_AUTH_TOKEN" } `
  -ContentType "application/json" `
  -Body $body
```

For the analyst shortlist use `POST /v1/shortlist` with each query's requested
`working_medium` (`GAS`, `LIQUID`, or `UNKNOWN`). Each result contains the
candidate pool and evidence, with conflicting media separated into
`blocked_candidates`. A medium match still requires human review; it does not
establish product suitability or gas certification.

Response contract:

```json
{
  "request_id": "uuid",
  "results": [
    {
      "input": "Кран шаровой муфтовый Ду25",
      "status": "MATCHED",
      "matched_name": "...",
      "matched_article": "...",
      "score": 0.031,
      "confidence": 0.96,
      "error_code": null
    }
  ],
  "latency_ms": 1234.5
}
```

For `NOT_FOUND`, `matched_name`, `matched_article`, `score`, and `confidence` are null. One product failure does not fail the rest of the batch; that item gets `status=ERROR`.

`score` is the existing retrieval score used by the champion and `confidence` is the reranker's reported confidence; neither should be treated as a calibrated probability without separate calibration.

The maximum batch size is controlled by `API_MAX_BATCH_SIZE`.

## Inference admission, load and provider budget

Both `/v1/match` and `/v1/shortlist` share the **same** process-local
admission gate, before any retrieval/DeepSeek/OpenAI call. Configure in `.env`:

```ini
API_MAX_BATCH_SIZE=100
API_MAX_INFLIGHT_BATCHES=1
API_MAX_ITEMS_PER_HOUR=500
```

- Only one batch can execute expensive matching at a time by default.
  Another request receives HTTP **429** with a stable
  `detail.code=MATCHER_BUSY` and `Retry-After`, rather than piling up threads.
- The quota charges **items attempted**, not requests. A 100-product batch
  consumes 100 units; failed provider attempts are **not refunded**.
  Exhaustion returns HTTP **429** with `HOURLY_ITEM_LIMIT_REACHED` and
  `Retry-After`; batches larger than the hourly limit are rejected.
- Reservations and the rolling 60-minute window are per **one Uvicorn worker**.
  They reset on restart and are not synchronized across replicas. They are
  **not** guaranteed dollar budgets or LLM-token budgets; configure a monetary
  spending cap with OpenAI/DeepSeek and an ingress/global rate limit as needed.
- Products in a batch still run **sequentially**; this patch deliberately
  prefers bounded safe execution to untested shared matcher parallelism.
  There is no promise of lower single-batch latency.

Gas/liquid use remains a **critical compatibility distinction**.
Shortlist results are never automatically approved, liquid-only candidates for
gas requests go in `blocked_candidates`, and UNKNOWN medium or UNVERIFIED gas
certification always needs expert review. The intentionally omitted comparison
of construction length and individual gas species is for historical GOLD
scoring only; it does not authorize physical installation.

## Live E2E and migration checks

CI tests on **real isolated PostgreSQL 16** that a legacy row survives migration
`0002_request_history_surrogate_id.sql` and a second snapshot with the
**same** `X-Request-ID` is inserted independently. It also checks the item view
has `history_id` per snapshot. This is separate from a real external-model E2E.

For real-stack validation, first configure API secrets and materialize the
Qdrant snapshot with `git lfs pull`, then start the stack:

```powershell
docker compose up -d --build
docker compose ps
$env:API_AUTH_TOKEN = ((Get-Content .env | Where-Object { $_ -match '^API_AUTH_TOKEN=' }) -split '=', 2)[1]
uv run python scripts/smoke_production_e2e.py --base-url http://127.0.0.1:8000
```

This makes **two real provider-backed matching calls**: one gas shortlist and
one liquid match using the same `X-Request-ID`. It checks health/readiness,
review-only and gas/liquid safeguards, and valid response snapshots without
assuming any particular LD ID. It deliberately fails if no shortlist candidates
are retrieved. Therefore it can consume API credits.

To verify the actual two PostgreSQL snapshots as well, supply a read-capable
`RAG_TENDER_SMOKE_READ_DSN` in the shell (do not commit the password), and
add `--verify-history`. The runtime `rag_tender_api` role is intentionally
**INSERT-only**, not a suitable smoke-test read account.

```sql
SELECT history_id, request_id, created_at, status, request_json, response_json
FROM rag_match_requests
WHERE request_id = '<id output by smoke>'
ORDER BY created_at, history_id;
```

**Before rollout to a populated production database**, take a verified
PostgreSQL backup. The additive migration changes the table's primary key
from the client-supplied request identifier to a generated UUID; the
`request_id` column stays intact as a non-unique indexed correlation label.
The migration is transactional and preserves existing request/response JSON.
New runtime startup refuses an unmigrated schema. Validate the migration on
a copy of the real DB before first production start.

## Request history

Every completed matching API call is written to PostgreSQL table `rag_match_requests` with a unique generated `history_id` per snapshot, including:

- request ID and timestamps;
- full request JSON;
- full response JSON;
- total latency;
- product count and match count;
- HTTP/status information;
- request-level error, when present.

Database schema changes are stored under `migrations/` and tracked in
`rag_schema_migrations`. Compose runs this migration step before the API. For
manual deployments, apply the SQL migration and record its version before
starting the service.

Inspect recent calls:

```powershell
docker compose exec postgres psql -U rag_tender -d rag_tender -c "SELECT created_at, request_id, status, product_count, matched_count, latency_ms FROM rag_match_requests ORDER BY created_at DESC LIMIT 20;"
```

## Tests

The repository's full test suite also needs the existing review extra:

```powershell
uv sync --extra test --extra review
uv run python -m pytest -q
```

Quick production-contract test:

```powershell
uv sync --extra test
uv run python -m pytest -q tests/test_production_api.py
```
