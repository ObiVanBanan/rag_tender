# Repository research: analyst shortlist and production boundaries

## Scope and method

Evidence was collected from the current `codex/competitor-resolver-v2` snapshot at commit `38f596f8691fd664b41c6f4ce155cc340e5f31b3` (the checkout is detached). The existing changes in `docs/EXPERIMENTS.md`, `docs/PRODUCT_DECISION_E08_SEED53.md`, and the Qdrant LFS snapshot were present before this work and are preserved.

## Current structure

- `src/nomenclature_matcher/api.py` owns FastAPI request/response schemas, middleware, health endpoints, and `/v1/match` orchestration.
- `src/nomenclature_matcher/production.py` builds infrastructure adapters and the application matcher. `match_products()` converts `MatchResult` into a one-product response.
- `src/nomenclature_matcher/matcher.py` orchestrates query interpretation, retrieval, technical prefiltering, and DeepSeek reranking. `MatchResult.candidates` retains the candidate pool; `MatchResult.selected` retains selected LD IDs, confidence, and reason.
- `src/nomenclature_matcher/models.py` contains dataclasses shared by retrieval and matching. `query_constraints.py` contains domain-like attribute extraction and matching rules, but it also depends on OpenAI and mixes parsing, matching, and product snapshots.
- `settings.py` provides environment-backed settings. Retrieval and reranker limits are independently configured; the current default hybrid rerank limit is 20.
- Existing durable request history is written by the `/v1/match` route through `ProductionRuntime.history`.

## Relevant behavior and gaps

1. The current API exposes one selected product, so analysts cannot audit the full top-20 and per-candidate evidence through the ordinary response.
2. `query_constraints._medium_values()` reads only structured product property `Рабочая среда`; exact-string comparison in constraint evaluation does not model gas/liquid categories.
3. No structured certification field or source of certification evidence was found in `LDProduct`, `SearchCandidate`, or `settings.py`. A gas claim therefore cannot be certified by this code.
4. The user's policy treats gas versus water/liquid as critical, while individual gas species and construction length are excluded from this GOLD comparison. This is an evaluation policy, not evidence of physical interchangeability.
5. The product decision artifact limits the proposed use to an analyst shortlist, not automatic substitution or purchasing.

## Integration and operational constraints

- Preserve `/v1/match` response compatibility.
- Use the already retrieved candidate pool; a shortlist request must not trigger a second retrieval or a second model call.
- Persist shortlist request and response using the existing history mechanism, subject to its current best-effort write behavior.
- Keep full candidate details and source properties in the shortlist payload for analysis. Treat names, properties, reasons, and URLs as untrusted catalog/model data.
- Fail closed: explicit liquid-only candidates must not appear in the gas suggestion list; unknown medium remains review-required; every candidate remains human-reviewed; gas certification is unverified.

## Evidence limits

No runtime request, Docker startup, or test suite was executed during this research pass. The repository snapshot and code paths above are the evidence base. Catalog-wide medium-value coverage and certification data availability remain unverified.

## Refactoring completed after this inspection

- Added `application.matching` and `application.shortlist`, with a shared `MatcherPort` contract.
- Extracted the phase policy to `domain.medium` and reused it in both shortlist display and hard-constraint evaluation.
- Moved PostgreSQL history persistence to `infrastructure.postgres_history`; `production.py` remains the composition root and re-exports existing symbols for compatibility.
- Removed schema DDL from API startup. Request-history schema setup is now a versioned SQL migration applied by a Compose one-shot service; runtime startup verifies the version.
- Runtime construction now registers close callbacks as clients are created and transfers them to `ProductionRuntime`; partial startup failures unwind acquired resources in reverse order.
- Candidate selection, second-chance retrieval, model reranking, and hybrid candidate search have been extracted from `NomenclatureMatcher` into application services with legacy matcher methods delegating to them.
- The unused DeepSeek constraint extractor was moved out of the query-constraint policy module into infrastructure, removing that module's direct OpenAI client dependency.
- Added production bearer authentication, fail-fast configuration for empty secrets, and loopback-only default API publishing. Detailed boundary map and remaining risks are in `design/architecture.md`.

These are partial bounded-context extractions; query interpretation/enrichment still sits in `NomenclatureMatcher`, and API route orchestration remains to be decomposed. Docker was not started. Compose configuration and Python/OpenAPI static checks were run after supplying temporary placeholder environment values; no test suite was run.
