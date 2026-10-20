# E08 frozen-100 seed 53 — review of GOLD labels

**Historical benchmark:** 34/100 existing PASS, 66/100 other Top-1, with **no changes to the frozen v1 dataset or model**. This is a DEV evidence review, not a new benchmark. Full GOLD and candidate LD identities remain outside GitHub.

## Updated adjudication rules (20 October 2026)

Per product owner's business criteria, **face-to-face / construction length is not a blocking GOLD condition** in this use case. It is not used to reject an otherwise suitable analogue. Where it changes installation requirements it can be noted to the operator, but not independently scored as a failure.

**Working medium must not be guessed from a legacy mapping or a one-word LD category.** Evaluate it in this order:
1. The customer's explicit medium or exact manufacturer's stated mandatory application, if any.
2. Exact LD product **supported-media list and certifications**, not just its catalogue's headline `Рабочая среда: Жидкость/Газ` classification.
3. Missing medium on the competitor request is **UNKNOWN**, not an implicit gas requirement merely because older GOLD contains `Gas` products.
4. The relevant gas-regulatory use (e.g., public gas distribution) may require special documentation or certification even if methane appears among allowed fluids; document this separately.
5. Distinguish `под электропривод` from installed electric actuation, check bore, DN, PN, material, joining and other explicit requirements independently.

## Exact reassessment of 11 previous “medium conflict” flags

The previous blanket flag **SOURCE_MEDIUM_DIFF was misleading** and is replaced with three evidence categories:

| Case | What is actually in E08 | Revised finding |
|---|---|---|
| **#2 TEMPER 99220015 MAX** | Source resolver: **gas**; selected LD is **Gas**; legacy GOLD products are labelled **liquid** | **No medium mismatch in selected answer**. The mapping/GOLD is potentially narrower or differently classified; assess other explicit constraints independently |
| **#35 ALSO КШ.ФПА.GAS.032.16-03** | Competitor is explicitly GAS; selected LD product **name and variant are Gas**, but exported `working_medium_json=[]` | **Missing LD medium field, not a proven conflict**; verify official card/certification |
| **#18,#20,#42,#70,#74,#76,#84,#88,#98 ALSO** | The original request does **not explicitly say gas**. Legacy GOLD entries are gas products; selected LD are classified “liquid” | **Media requirement unspecified**, not a demonstrated mismatch. Judge on independent allowed-media evidence and remaining engineering constraints |

### Case #98 is especially informative

ALSO `КШ.Ф.250.16-01` → selected LD ordinary flanged DN250/200 PN16, steel 20, **LD ID 1273**.

- Primary field on LD official card: `Рабочая среда: Жидкость`.
- **Same official card's `Допустимые рабочие среды` list includes methane, biogas, butane gas and gaseous propane** as well as water. Thus “LD liquid cannot work with gas” is **false as an absolute claim**.
- Original competitor text does not require gas; it also does not establish a specific gas-network certification. Mark **strong candidate for expanding a separately versioned GOLD-v2**, requiring a final service/certification judgement only if the use case demands one.

Sources:
- https://xn--d1an.xn--p1ai/products/1273--kran_sarovoj_ld_kscf_iz_stali_20_du250_200_ru1_6mpa/
- https://alsoarm.com/series/rs-series/ (RS application includes heating network water *and* certain gaseous media)
- https://alsoarm.ru/series/gas-series/ (dedicated GAS series and use in gas distribution)

## Other unresolved questions (not construction length)

- **#18,#42,#84**: “под редуктор/электропривод” was mapped to hard `control=electric`. This is about actuator readiness rather than installed drive and remains a material review issue.
- **#1,#91**: Special anti-vandal and underground installations. Check whether these executions are appropriate.
- **#2,#67**: The term `MAX` denotes a series/variant; assess required performance, not length itself.
- **#3,#70**: Earlier review used *length-only* rejection. That rejection is now **withdrawn** under owner's criteria. Both go to positive analogue review by their other mandatory parameters, not automatically into GOLD.
- **#98**: Candidate technically close; gas/liquid label alone no longer prevents addition.

## Current annotation accounting

- 34 already-in-GOLD PASS retained (cases 4,7,8,13,15,21,22,26,33,37,39,40,45,47,51,52,56,58,59,60,61,62,63,71,72,78,82,83,86,89,94,95,96,97).
- 66 non-GOLD responses remain under review. **Do not infer that all are technically wrong.**
- 0 additional rows written into GOLD-v2 **yet**: requests alone are not signed-off installation/design specifications, and the technical review has not been converted into new authorized labels.
- The `docs/gold_e08_seed53_decisions.csv` contains all 100 case-level remarks with corrected medium categories. No answer-bearing LD/GOLD IDs are in that public CSV.
- Original `competitor_analog_hit_any_min_v1`, SHA, E08 Top-1 and original mapping remain unchanged.

A future approved GOLD-v2 overlay must be versioned and explicitly separated from frozen E08 v1 scoring. Never place private acceptable ID answers in runtime resolver prompts, holdout or agent optimization state.