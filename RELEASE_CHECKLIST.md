# RAG Tender — release readiness

**Candidate:** catalog-first Technical Preview · **Date:** 2026-10-30 · **Target:** `main` as a demo/reference source tree, **not** unattended production deployment.

## Verified during repository inspection

- [x] API and catalog-first runtime code exists in the integration source branch.
- [x] Source registry and schema descriptions for MARSHAL / ALSO / TEMPER present.
- [x] README / architecture / API / quality and demonstration docs are aligned with selected branch capabilities.
- [x] Composer override default API port documented as 8002; Qdrant LFS pointer rejection added to override.
- [x] README distinguishes verified DEV observations from independently validated release performance.

## Technical-preview checks and remaining production gates

- [x] `uv sync --locked --extra test` + `uv run python -m pytest -q tests`: **245 passed, 1 deprecation warning** on integrated release tree [CI run 40996468713](https://github.com/ObiVanBanan/rag_trend/actions/runs/40996468713).
- [x] `docker compose config --quiet`, PostgreSQL 16 migration smoke and Docker image build passed in the same [CI run](https://github.com/ObiVanBanan/rag_trend/actions/runs/40996468713).
- [ ] Live E2E with real OpenAI/DeepSeek/Qdrant/PostgreSQL and correctly materialized LFS snapshot.
- [ ] `scripts/smoke_production_e2e.py --base-url http://127.0.0.1:8002 --verify-history` against authorized demo instance and read-only database DSN.
- [ ] Untouched HOLDOUT benchmark and separate industrial-domain review of dangerous false matches.
- [ ] Secret scan of reachable tree **and Git history**, revoke/rotate exposed credentials; investigate existing credentials cutover issue #6.
- [ ] Confirm rights to share LD CSV, Qdrant snapshot and competitor sources; determine public code license.
- [ ] Test PostgreSQL migration & rollback on a copy of target data; verify restores and persistence.
- [ ] TLS reverse proxy, network ACL, external provider spending limits, log redaction and history retention policy.
- [ ] Capture owner-approved demo evidence/screenshots from **actual** output, without client data or leaked credentials.

**Note:** GitHub CI validates the source/build; it does not perform live calls to OpenAI/DeepSeek or verify the externally supplied LD CSV against a real index. A green badge does not certify industrial compatibility.

## Decisions / exclusions

- No silent merge of the separate UI/CSV-first experiments; they require contract and end-to-end integration tests.
- Never present a retrieval confidence number as physical suitability or gas certification.
- No tag / GitHub Release with `production-ready` wording until the gates above are complete.

## Useful commands

```bash
uv sync --locked --extra test
uv run python -m pytest -q tests
docker compose config --quiet
docker compose up -d --build
API_AUTH_TOKEN=... uv run python scripts/smoke_production_e2e.py --base-url http://127.0.0.1:8002
```

Run only with properly configured external data and secrets. Do not paste real keys into terminals recorded on screen; set them locally outside version control.
