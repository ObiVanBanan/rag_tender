# Product decision — E08 seed 53 competitor matching

**Decision: launch a supervised analyst shortlist pilot only. Do not enable automatic substitution or purchasing.**

## Evidence

- Same saved 100-case DEV run: GOLD v1 top-1 was 34/100; current reviewed GOLD v3 is 39/100. Five newly approved alternatives were already the model's returned IDs; no inference or retrieval was rerun.
- Reviewed GOLD v3 top-20 candidate coverage is 84/100. Wide RRF pool coverage remains 92/100.
- DeepSeek's selected list contains a GOLD v3 ID in 45/100; the returned top-1 is correct in 39/100, leaving 6 cases where an acceptable selection was not returned first. 16 queries have no reviewed GOLD ID in top-20.
- The independent audit of 30 selected answers rejected 26, approved #74, and left #29, #34, and #50 for review. It does not validate all original GOLD entries or the remaining cases.
- The reviewed metric deliberately ignores construction length and gas species. Gas versus water/liquid stays critical, as do size/pressure, joint type, bore, material where specified, actuation, and special execution.
- The production API currently exposes one selected match by default. The 100-case detailed top-20 table is an offline trace, not a shipped review UI.

## Pilot contract

1. Present ranked candidates with manufacturer/article, catalog attributes, provenance and per-field comparisons.
2. Ask for the working medium when it is absent. Do not treat unknown medium or a product name containing a gas species as gas-service approval.
3. Block a gas query when the candidate is confirmed water/liquid-only or gas certification is unverified; route it to a human reviewer.
4. Preserve the critical checks in the evidence section above. Ignore only `L` and individual gas-species differences in this particular GOLD metric.
5. Require a human sign-off before any substitute is used or purchased.

## Promotion gates

- Reconcile the GitHub draft's top-level description and historical v2 text with its latest v3 files: current `metrics_v2.json` says 39/100 and five additions, while the PR body and older section say 38/100 and four additions.
- Freeze a quality-reviewed GOLD version with source-backed answers and resolve the three exact-variant review cases plus the other unresolved labels.
- Add the hard medium/certification gate and a top-20 analyst response contract to the product API.
- Validate the frozen rubric on a separate holdout. Only then consider a broader pilot; require substantially higher, safety-stratified precision before autonomous action.

Detailed per-query evidence and the v3-scored top-20 are in `../.tmp/competitor_analog_100_seed53_gold_v3_report.md`, `../.tmp/competitor_analog_100_seed53_gold_v3_scorecard.csv`, and `../.tmp/competitor_analog_100_seed53_top20_gold_v3.csv` alongside the raw local run artifacts.
