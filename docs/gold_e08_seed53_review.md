# E08 frozen-100 seed 53 — GOLD adjudication (audit, no runtime changes)

**Status: decision log only. 34/100 original PASS; 66/100 non-GOLD Top-1; 0/66 newly approved GOLD alternatives.** No matcher changes. The **frozen v1 benchmark remains bit-for-bit unchanged** and its 34% Top-1 remains the historical metric.

## Evidence and decision policy

Sources: E08 trace `32ff3fba`, full case-wise top-20 + selected LD and original GOLD from the owner's **local** CSV, original `mapping_results.csv`, and independent manufacturer/LD product documents for investigated discrepancies.

A non-GOLD response matching DN/PN/material/connection is **not enough** to approve an LD alternative. Review the original mapping's **working medium, type of actuation, full/reduced bore, connection arrangement and special variant**, as well as **construction length, flange geometry and actual model/series**. Unknown does not mean compatible. Manual/gearbox vs actuator-ready/installed are distinct.

All 66 non-GOLD responses remain **`REVIEW_REQUIRED_NO_GOLD_CHANGE`**. No additional acceptable IDs are introduced merely because a matcher chose them. Keep full candidate/GOLD lists and product identities outside GitHub in the owner's private audit data; only anonymized case numbers/reasons appear here.

## Specific source-verified examples

| DEV case | Finding | Outcome |
|---|---|---|
| #3 ALSO `КШ.Ф.З.150.25-01` | Special gate-valve-length configuration **L=280 mm**; selected ordinary LD **L=380 mm** | **Do not add**. Face-to-face mismatch |
| #70 ALSO `КШ.Ф.П.040.40-03` | ALSO **L=200 mm**, selected LD **L=290 mm**, despite matching DN/PN/grade/full bore | **Do not add**. Dimensional incompatibility |
| #98 ALSO `КШ.Ф.250.16-01` | DN250, PN16, bore 200 mm, **L=530 mm** and flange geometry coincide, but original mapping records **gas**, while the proposed LD catalogue entry is **liquid** | **Do not add** until medium requirement is resolved |
| #18, #42, #84 ALSO | The wording «под редуктор/электропривод» was parsed as the single hard value `electric`; actuator-ready is not an installed electric drive | **Do not add** without checking actual requested actuation |
| #2, #67 TEMPER MAX | Special MAX construction/length must be independently verified | **Do not add** on DN/PN alone |
| #1 MARSHAL | Proposed LD has extra anti-vandal configuration and source mapping differs on actuation | **Do not add** without engineering review |
| #91 MARSHAL | Proposed LD is a special underground installation execution, not specified as such by the source | **Do not add** |

The original source mapping is also **not automatically authoritative**: contradictory gas/liquid or actuator fields need the official competitor catalogue or original tender specification before relabelling.

## All 100 decisions (case numbers for the E08 seed-53 order)

- **Existing PASS, unchanged — 34:** 4,7,8,13,15,21,22,26,33,37,39,40,45,47,51,52,56,58,59,60,61,62,63,71,72,78,82,83,86,89,94,95,96,97.
- **Disputed/non-GOLD, unchanged — 66:** all other case numbers 1–100.
- **Actuation mismatch vs source mapping — 34:** 1,5,6,10,11,14,18,24,25,27,29,36,38,41,42,43,44,46,49,50,55,57,65,66,68,73,77,81,84,90,91,92,99,100.
- **Service-medium discrepancy vs source mapping — 11:** 2,18,20,35,42,70,74,76,84,88,98.
- **ALSO RS geometric/fit check — 11:** 18,20,29,34,64,76,79,84,85,88,93.
- **Explicit actuator-readiness ambiguity — 3:** 18,42,84.
- **Extra kit/configuration — 3:** 10,46,92.
- **TEMPER MAX dimensions — 2:** 2,67.
- **Underground/anti-vandal special execution — 2:** 1,91.
- **Requires independent engineering proof (no categorical problem established yet) — 18:** 3,9,12,16,17,19,23,28,30,31,32,48,53,54,69,75,80,87.

Groups overlap: a case may have more than one unresolved constraint. This is a **review queue**, not an assertion that every non-GOLD response is wrong.

## References

- ALSO 2025 official technical catalogue (gate-valve face-to-face dimensions): https://dn.ru/storage/certificates/also/kran-sharovoj-2024/katalog_also_dlya_zhidkih_sred_2025.pdf
- ALSO full-bore flange reference, L=200 for `КШ.Ф.П.040.40-03`: https://also.pro-solution.ru/wp-content/uploads/2020/03/fullprice.pdf
- LD selected product #70, official L=290: https://xn--d1an.xn--p1ai/products/2463--kran_sarovyj_ld_kscf_iz_stali_12h18n10t_du40_ru4_0mpa_polnoprohodnoj/
- ALSO `КШ.Ф.250.16-01` construction and flange geometry: https://www.air-gaz.ru/catalog/vodosnabzhenie-kanalizatsiya/krany-sharovye-stalnye-i-polietilenovye/krany-sharovye-stalnye-voda/kran-sharovoy-flantsevyy-kshf-voda/
- LD official selected product #98 (gas/liquid and L): https://xn--d1an.xn--p1ai/products/1273--kran_sarovoj_ld_kscf_iz_stali_20_du250_200_ru1_6mpa/

## Versioning and anti-leakage

1. Preserve `competitor_analog_hit_any_min_v1`, frozen SHA/seed/order and old E08 score.
2. Correct benchmark labels **only after** confirming exact substitute compatibility and provenance. No additions passed that bar in this conservative review.
3. If signed off later, put approved rows into a separately versioned **private** GOLD-v2 overlay and document their effect on scoring **separately**; do not rewrite E08 v1 measurements or tune against final holdout.
4. Do not expose acceptable/selected LD IDs to resolver, RAG, agent prompts, adaptive optimizer or public DEV traces.

The complete 100-row explanation file is available to the owner as `E08_gold_review_100_decisions.csv` outside this repository.