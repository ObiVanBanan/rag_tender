# Changelog

This changelog describes **source-level release candidates**, not deployments. See [release gates](RELEASE_CHECKLIST.md).

## Unreleased — Technical Preview (2026-10-30)

### Integrated from the catalog-first development line

- FastAPI: `POST /v1/match` and analyst `POST /v1/shortlist`.
- Hybrid LD retrieval: OpenAI embeddings / Qdrant dense, BM25 from LD CSV, RRF, technical filtering, DeepSeek reranking.
- MARSHAL / ALSO / TEMPER source-backed designation / article decoding, provenance and conservative UNKNOWN; verified exact-product conflicts fail closed.
- Separate PostgreSQL history snapshots, API authentication, process-local admission, health and metrics.
- Versioned SQL migrations and production-oriented Compose container profile.

### Documentation and demo readiness

- Product README, architecture diagrams, API, installation, quality limitations, demo script, and release checklist.
- Corrected default Compose port (8002 with the committed override); restore script now rejects Git LFS pointer files before attempting snapshot recovery.
- Enabled production API CI workflow for main and release branches (a configured workflow **does not** mean checks have passed).

### Known limitations

- No integrated business UI / CSV-first fallback in this candidate; see separate work in PRs #22 and #27.
- No verified provider-backed E2E, independent final holdout or production rollout in this preparation session.
- Required LD catalog export is not distributed in this candidate; Qdrant binary snapshot must be obtained via LFS with appropriate rights.
- Public source code has no chosen OSS license; copying/redistribution may require separate approval.
- This is **not** a guarantee of engineering interchangeability, gas certification or unattended procurement suitability.

## Historical MVP (September 2026)

- CLI-first nomenclature matcher, dense/BM25/RRF, reranker and evaluation harness on legacy `main`.
