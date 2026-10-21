# ADR: Domain-gated analyst shortlist for competitor matching

## Status
Accepted for implementation in this isolated branch; production rollout remains pending review.

## Task
Expose the complete reranker candidate pool and evidence to analysts while ensuring product matching never claims automatic interchangeability.

## Research Inputs
- `research_report.md`: current API, matcher pipeline, candidate structures, medium metadata gap, and compatibility constraints.
- `docs/PRODUCT_DECISION_E08_SEED53.md`: analyst-shortlist-only product boundary and GOLD policy.

## Context
The current `/v1/match` route returns a single chosen product. The matcher already holds up to 20 retrieval candidates and the reranker selection details. Product medium is unstructured text in the `Рабочая среда` property. There is no structured certification evidence. Explicit gas-vs-liquid mismatch is safety-critical; individual gas species and construction length are excluded from this evaluation policy.

## Decision
Add a separate `POST /v1/shortlist` use case. Require the requested medium for every query. Build up to 20 candidate records from the existing `MatchResult`; join reranker selection rank, confidence, and reason by LD ID. Use a pure domain policy to classify explicit catalog medium values as GAS, LIQUID, BOTH, or UNKNOWN. GAS requests exclude explicit LIQUID-only products from suggestions and return them only in a separately marked blocked list. Unknown catalog medium remains visible as `NEEDS_EVIDENCE`. Even a matching phase is marked `MEDIUM_MATCH_REVIEW_REQUIRED`; this does not establish product suitability. All returned items and results require human review; gas certification is always `UNVERIFIED`. The endpoint never returns an auto-approval decision.

The domain classifier intentionally ignores construction length and treats named gas species as GAS for evaluation. It does not infer certification from product name, model output, or search rank. The existing technical constraint evaluator uses the same phase policy so exact species strings do not discard gas candidates before ranking.

## Alternatives
### Option A: Extend `/v1/match`
- Pros: one endpoint.
- Cons: breaks clients and overloads the existing one-result contract.
- Decision: rejected; retain compatibility with a separate endpoint.

### Option B: Run a separate broad retrieval for shortlist
- Pros: could produce more candidates than the reranker pool.
- Cons: duplicate latency/cost and candidate provenance mismatch.
- Decision: rejected; expose the existing candidate pool and report its bounded size.

### Option C: Claim compatibility from model confidence
- Pros: simple response.
- Cons: model confidence is not safety certification and structured medium coverage is incomplete.
- Decision: rejected; explicit domain gate and analyst review are mandatory.

## Contracts
### API
`POST /v1/shortlist` accepts `{ "queries": [{"query": "...", "working_medium": "GAS|LIQUID|UNKNOWN"}], "max_candidates": 20 }`. `max_candidates` is constrained to 1..20. If the query has no explicit medium, the application adds the selected phase to the internal matcher query; if an explicit medium conflicts with the API field, validation rejects the request. The response includes request ID, latency, result status, requested medium, `human_review_required=true`, `automatic_approval=false`, review-required candidates, blocked candidates, rank, attributes, raw properties, reranker details, and certification status. Existing `/v1/match` is unchanged.

### Data
Reuse existing product and request-history data. Versioned SQL migrations are applied by a one-shot Compose service before API startup and recorded in `rag_schema_migrations`; the runtime adapter verifies the required version and does not mutate schema. Candidate evidence is a response snapshot; source URLs and raw properties are passed through as catalog evidence.

### Events / Jobs
Matching is synchronous; no queue or retries. Each query invokes the existing matching pipeline once. Startup runs Qdrant restore and database migration one-shot jobs before API readiness.

### Errors
Per-query matching exceptions become `ERROR` with a stable error code; exception text is not returned in the shortlist payload. Invalid request media or limits are rejected by Pydantic with HTTP 422. No candidates yields `NO_CANDIDATES`.

## Security
Validate non-empty query and bounded batch/top-k sizes. Do not trust catalog text or model rationale as executable instructions. Do not expose secrets. Never turn `UNVERIFIED` certification or `UNKNOWN` medium into a positive safety claim. Production requires a 32-character bearer token; health and API schema/docs are public, while operational routes require bearer auth. The OpenAPI schema advertises this contract. Default Compose publishing is loopback-only, with remote access expected through TLS termination. Rate limiting and abuse controls remain deployment requirements before internet exposure.

## Testing Strategy
Verification completed for this branch: the full Python suite covers domain medium policy, shortlist ranking and blocked-candidate separation, API batch bounds and history persistence, bearer auth, legacy `/v1/match`, architecture import boundaries, and request-history recorder success/failure including telemetry failure isolation. The API integration tests use an in-process TestClient; isolated database migration and adapter checks are documented in `plan/implementation_plan.md`. Manual analyst review of representative candidate payloads and full deployment acceptance with project credentials remain release gates.

## Consequences
Analysts receive auditable top candidates and provenance without extra model calls. The response is larger and may include raw property text. The shortlist is bounded by the current matcher pool, not a guarantee of top-20 across the full catalog. Schema changes are explicit migration artifacts. Rollback is removal of the new route and domain service; migrations are forward-only and must be assessed before rollback. A future certification feature requires a trusted structured source and provenance model.

## Open Questions
- Does the production catalog consistently populate `Рабочая среда` and which exact variants occur across all products?
- Which trusted source should provide certification scope, standard, expiry, and evidence URL?
- What rate limit and abuse controls should accompany bearer authentication before internet exposure?
