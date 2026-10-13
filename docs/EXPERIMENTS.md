# Experiments

Short decision history for frozen-100 DEV runs. Per-case traces and full GOLD-bearing outputs stay in `.tmp`; commit-safe DEV traces live under `docs/experiments/traces/`.

## Current checkpoint

Branch: `codex/competitor-resolver-v2`  
Current HEAD: `b733910`  
Best measured DEV result: **E07-CAT**

Decoder baseline:
- top1: 26%
- initial recall: 66%
- rerank recall: 67%

Current resolver-only best:
- top1: **30%**
- initial recall: **62%**
- rerank recall: **62%**
- pre-truncation pool recall: **92%**
- catalog-resolved strategy: **93/100**
- runtime web: **OFF**

The architecture is no longer blocked by source understanding in the same way as E04. The remaining failures are split between:
- `RETRIEVAL_MISS`: 37
- `RERANK_SELECTION`: 32
- `FILTER_DROP`: 1
- success: 30

The exact causes inside those buckets were **not known from E06**, so stage-wise tracing was added before attempting more tuning.

## What is already decided

| Topic | Decision | Evidence |
|---|---|---|
| Legacy decoder | Benchmark/control only; not production runtime | E01–E03 |
| Exact vs family identity | Must be separated | E02 regression |
| Catalog-first resolver | Keep | E04 + E06 |
| TEMPER/MARSHAL/ALSO schemas | Keep | E04 + E06 |
| Runtime web | Disabled/deferred | E05, ADR-001 |
| GOLD leakage | Never expose acceptable LD IDs to resolver/retrieval | all resolver-v2 work |
| Final unseen holdout | Do not touch yet | current evaluation policy |
| Next optimization | Must be chosen from stage trace, not intuition | instrumentation milestone I01 |

## Ideas considered but not yet proven

These are **not implemented conclusions** yet:

- increasing candidate limit / keeping a larger RRF pool;
- filtering before final top-k truncation;
- changing dense/BM25/RRF weights or retrieval query representation;
- structured candidate facts for reranker;
- deterministic compatibility scoring before LLM rerank;
- replacing or cascading the reranker;
- BROEN catalog coverage;
- reintroducing web with a better provider;
- running the final 1000/unseen holdout.

Do not describe any of the above as a confirmed bottleneck or fix until E07 localizes the current failures.

---

## E01 — Competitor decoder baseline
Commit: `08e2497`
Setup: frozen-100 DEV; decoder v1 baseline.
Hypothesis/change: decode competitor designations into technical facts before LD retrieval.
Metrics: top1 26%; initial GOLD recall 66%; rerank GOLD recall 67%.
Failure split: not preserved in the aggregate report.
Conclusion: decoder established the candidate-recall baseline.
Decision/next: compare resolver approaches against this baseline; keep GOLD hidden from source understanding.

## E02 — Competitor resolver v1
Commit: `df8b584` (initial resolver); result recorded in PR #13.
Setup: frozen-100 DEV; resolver integrated with the decoder path.
Hypothesis/change: resolve competitor facts from a persistent, provenance-aware KB/catalog before retrieval.
Metrics: top1 21%; initial GOLD recall 56%; rerank GOLD recall 55%.
Failure split: family identity could be stored and reused as an exact product; numeric stage counts were not preserved.
Conclusion: resolver integration regressed from the 26% / 66% / 67% decoder baseline; family and exact-product identity were conflated.
Decision/next: separate family from exact variant identity and prevent family facts from populating exact product records.

## E03 — Decoder-precedence gate diagnostic
Commit: `50b2b92`
Setup: same frozen-100 DEV evaluation; decoder precedence enabled over resolver v1.
Hypothesis/change: gate resolver use to avoid disturbing products handled by the deterministic decoder.
Metrics: top1 25%; initial GOLD recall 63%; rerank GOLD recall 64%; resolver strategy count 44 → 0.
Failure split: remaining gap was not split by pipeline stage in the saved summary.
Conclusion: the v1 regression came from resolver interaction with decoder-covered MARSHAL/ALSO cases; precedence hides the regression without solving source understanding.
Decision/next: retain the diagnostic as evidence, but make resolver-only exact identity the target architecture.

## E04 — Resolver v2, TEMPER schema
Commit: `0eedf9f`
Setup: frozen-100, seed 53, fresh KB, decoder OFF, runtime web ON.
Hypothesis/change: resolver-only exact identity plus a generic TEMPER catalog schema can resolve exact products without decoder logic.
Metrics: top1 8%; initial recall 22%; rerank recall 22%; TEMPER top1 4/8, initial 6/8.
Failure split: `RETRIEVAL_MISS` 78/100.
Conclusion: catalog/schema resolution works where catalog knowledge exists; missing MARSHAL/ALSO coverage dominates the regression.
Decision/next: add MARSHAL/ALSO catalog schemas. Do not tune the reranker while candidates are missing.

## E05 — Resolver v2, runtime web
Commit: `0eedf9f` (web-on run; decision documented in `56c1c15`).
Setup: same frozen-100, seed 53, fresh KB, decoder OFF; runtime web ON.
Hypothesis/change: use live search to recover unresolved competitor products and improve technical retrieval queries.
Metrics: web accepted 3; rejected 54; skipped 43; accepted results produced 0 useful technical-query paths.
Failure split: all 3 accepted contexts ended as `web_context_no_technical_query`; no new resolver retrieval path was produced.
Conclusion: runtime web added latency and result noise without demonstrated recall gain.
Decision/next: disable runtime web; retain search for offline knowledge acquisition. See [ADR-001](decisions/ADR-001-runtime-web-search.md).

## E06 — Resolver v2, MARSHAL and ALSO schemas
Commit: `f2d6cc1`
Setup: frozen-100, seed 53, fresh KB, decoder OFF, runtime web OFF, workers 1.
Hypothesis/change: generic data-driven designation schemas for MARSHAL and ALSO restore candidate recall without manufacturer-specific matcher logic.
Metrics: top1 30%; initial recall 63%; rerank recall 63%; catalog-resolved strategy 91/100; web skipped 100/100. MARSHAL initial 30/42, top1 13/42; ALSO 27/47, 13/47; TEMPER 6/8, 4/8.
Failure split: `RETRIEVAL_MISS` 37; `RERANK_SELECTION` 32; `FILTER_DROP` 1; success 30.
Conclusion: initial recall rose from 22% to 63%, close to the 66% decoder baseline; top1 rose from 8% to 30%. Catalog-first source understanding is now viable.
Decision/next: **do not guess** whether retrieval or reranking is the next bottleneck. Add stage-wise tracing and classify E06-style failures first.

---

## I01 — Stage-wise trace instrumentation
Current HEAD: `b733910`
Type: instrumentation milestone, **not a quality experiment**.

Why:
E06 only told us that 37 cases were `RETRIEVAL_MISS` and 32 were `RERANK_SELECTION`. It did not tell us whether a retrieval miss meant:
- absent from dense/BM25 pool;
- present in the merged pool but truncated before top-k;
- removed by hard constraints;
- lost in second-chance retrieval.

Added diagnostics:
- resolver status and canonical facts;
- dense hits and BM25 hits;
- merged RRF pool before top-k truncation;
- initial top-k candidate snapshots;
- hard-filter checks;
- second-chance retrieval funnel;
- reranker input/status/reason/selections;
- exact git HEAD in the trace.

Benchmark failure substages:
- `MODALITY_POOL_MISS`
- `RRF_TRUNCATION`
- `HARD_FILTER:<field>`
- `RERANK_NOT_SELECTED`

Storage policy:
- full GOLD-bearing trace → `.tmp/`, never commit;
- DEV-safe trace without acceptable/GOLD IDs → `docs/experiments/traces/`;
- final unseen holdout traces must not be committed.

No ranking/retrieval behavior is intentionally changed by I01.

---

## E07-CAT — Catalog Expansion v1 + stage trace

Commit: `4152bcb`
Setup: frozen-100, seed 53, fresh KB, decoder OFF, runtime web OFF, workers 1.

Hypothesis/change:
- preserve TEMPER MAX as distinct exact identity;
- add TEMPER MAX catalog schemas;
- use stage-wise trace to localize downstream failures.

Metrics:
- top1: **30%**
- acceptable in pre-truncation RRF pool: **92%**
- initial recall after top-20: **62%**
- rerank recall: **62%**
- catalog-resolved strategy: **93/100**

Failure split:
- `RRF_TRUNCATION`: **30**
- `RERANK_NOT_SELECTED`: **31**
- `MODALITY_POOL_MISS`: **8**
- `HARD_FILTER:bore_type`: **1**
- success: **30**

Key findings:
- catalog expansion resolved more source products (91 → 93) but did not change top1;
- the dominant retrieval loss is now measured: 30 cases have an acceptable LD in the full RRF pool but lose it before the top-20 reranker input;
- 31 more cases reach reranker and still lose selection;
- one ALSO case exposed a schema bug: welded prefix `П` was incorrectly interpreted as full-bore in `КШ.П.Р...`.

Decision:
- keep Catalog Expansion v1;
- next intervention targets the measured RRF/top-20 bottleneck;
- fix ALSO bore semantics;
- do not change embeddings or LLM prompt in the same experiment.

## E08 — Wide RRF technical prefilter — PATCH READY, BENCHMARK PENDING

Behavioral change:
- retrieve up to 200 candidates from the already-produced RRF pool;
- apply explicit hard constraints **before** final top-k truncation;
- rank hard-eligible candidates deterministically using structured technical compatibility with the canonical resolver/query profile;
- unknown candidate facts are neutral;
- known technical conflicts hurt rank;
- ties preserve the original RRF order;
- send only top-20 to the existing LLM reranker.

Also:
- fix ALSO `КШ.П.Р...` so welded prefix `П` does not imply full bore;
- keep explicit full-bore body codes such as `ФП` / `ПП`.

E08 trace adds:
- `TECHNICAL_PREFILTER_DROP` when an acceptable LD existed in the wide pool but the new prefilter failed to keep it in top-20.

Acceptance questions:
1. Does acceptable-in-initial rise materially above E07-CAT 62%?
2. Does top1 improve above 30%?
3. How many of the old 30 `RRF_TRUNCATION` cases become reachable?
4. Does `TECHNICAL_PREFILTER_DROP` stay low enough to justify the new layer?
5. Does the ALSO schema fix remove the known `КШ.П.Р` source-understanding error?

Do not change reranker prompt until E08 is measured.

## Promotion rule

Do not run the final unseen holdout merely because top1 is above the old decoder baseline on frozen-100.

Promote only after:
1. E07-CAT is measured;
2. the dominant remaining failure is localized from its stage trace;
3. at least one targeted fix is validated on DEV without regression;
4. the candidate is frozen;
5. then run the untouched final holdout / final 1000 once.
