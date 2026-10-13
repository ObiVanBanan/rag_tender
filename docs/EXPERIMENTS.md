# Experiments

Short decision history for frozen-100 DEV runs. Per-case traces and full GOLD-bearing outputs stay in `.tmp`; commit-safe DEV traces live under `docs/experiments/traces/`.

## Current checkpoint

Branch: `codex/competitor-resolver-v2`  
Current HEAD: `b733910`  
Best measured DEV result: **E06**

Decoder baseline:
- top1: 26%
- initial recall: 66%
- rerank recall: 67%

Current resolver-only best:
- top1: **30%**
- initial recall: **63%**
- rerank recall: **63%**
- catalog-resolved strategy: **91/100**
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

## E07-CAT — Catalog Expansion v1 + stage trace — NEXT

Status: **patch ready; benchmark pending**

Why this experiment moved ahead of a pure diagnostic rerun:
- E04 and E06 already showed a large positive effect from catalog coverage;
- the user explicitly chose to continue the catalog-first hypothesis;
- stage-wise tracing remains enabled, so this run still localizes the remaining downstream failures.

Behavioral changes are restricted to the source-understanding layer:
- preserve numeric suffix variants such as `99020015 MAX` as a distinct exact identity `99020015max`;
- add official TEMPER MAX catalog schemas for `980/982/983/990/992/993`;
- do **not** infer material grade from the fixed `20` digits in MAX articles;
- keep ambiguous PN values unknown (for example TEMPER 992 DN300+ published as PN16/25);
- refresh official ALSO/BROEN catalog entry points without adding unverified BROEN parsing rules;
- no retrieval, RRF, hard-filter or reranker behavior is changed.

Known DEV gap targeted directly:
- `TEMPER 99020015 MAX`
- `TEMPER 99220015 MAX`

Important identity finding:
`99020015` and `99020015 MAX` are distinct official TEMPER products, so the previous numeric-only identity would have allowed KB collision.

Run setup:
- same frozen-100 DEV;
- seed 53;
- fresh KB;
- workers 1;
- decoder OFF;
- runtime web OFF;
- stage trace ON.

Command:

```powershell
uv run python scripts/eval_competitor_analogs.py \
  --sample 100 \
  --seed 53 \
  --workers 1 \
  --output .tmp/e07-cat-full-gold.json \
  --public-trace-output docs/experiments/traces/E07-CAT-seed53.json
```

Primary comparison vs E06:
- catalog-resolved strategy: 91/100 → ?
- initial recall: 63% → ?
- rerank recall: 63% → ?
- top1: 30% → ?
- unresolved source products: ? → ?

Secondary trace questions:
- remaining `MODALITY_POOL_MISS`;
- remaining `RRF_TRUNCATION`;
- hard-filter drops;
- `RERANK_NOT_SELECTED`.

Decision:
- keep Catalog Expansion v1 only if source coverage improves without regressing overall DEV quality;
- choose the next matching-layer change from the post-expansion trace, not from intuition.

## E08 — Targeted downstream fix — PENDING E07-CAT

Choose exactly one intervention from the trace:
- RRF truncation dominates → candidate-pool/filter-before-truncate experiment;
- modality pool miss dominates → retrieval/query/index experiment;
- hard-filter dominates → constraint provenance/evaluator fix;
- rerank-not-selected dominates → structured candidate facts / deterministic compatibility / reranker experiment;
- source-resolution misses still dominate → continue catalog ingestion.

Do not bundle retrieval, reranker and schema changes into one experiment.

## Promotion rule

Do not run the final unseen holdout merely because top1 is above the old decoder baseline on frozen-100.

Promote only after:
1. E07-CAT is measured;
2. the dominant remaining failure is localized from its stage trace;
3. at least one targeted fix is validated on DEV without regression;
4. the candidate is frozen;
5. then run the untouched final holdout / final 1000 once.
