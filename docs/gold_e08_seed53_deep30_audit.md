# E08 seed53 — independent catalogue audit of the remaining 30 OTHER_UNVERIFIED_TECHNICAL_VARIANT cases

**Audit date:** 2026-10-20. **Scope:** exactly the 30 non-GOLD cases previously marked `OTHER_UNVERIFIED_TECHNICAL_VARIANT` in `E08_gold_v2_seed53_complete_review.csv`.

## Result

- **26 cases — REJECT_CURRENT_RAG_CHOICE** because a critical characteristic is inconsistent (primarily drive/actuation or joint/bore).
- **1 case — APPROVE_GOLD_V3** (#74 ALSO, LD 1532): independently supported source medium and other mandatory attributes.
- **3 cases — REVIEW_REQUIRED** (#29, #34, #50): no conclusive exact product match from available independent evidence.
- **No changes to construction-length or gas-species waivers.** Distinguish gas-service vs liquid-service as critical. Driver/gearbox vs actuator-ready vs installed drive remains critical.

**IMPORTANT: 26 rejections are against the SELECTED RAG outputs only, not verification that the original GOLD candidates are correct.** Some original GOLD entries are themselves questionable: original MARSHAL `.6` / `.7` / `.9` actuated equipment had been mapped to LD products described only as *under electric actuator*, which is not the same as having the specific actuator installed. Thus the original mapping is not ground truth for that aspect.

### Manufacturer's marking, previously ignored

The [MARSHAL manufacturer's marking standard](https://lztamarshal.ru/support/tekhnicheskaya-dokumentatsiya/struktura-oboznacheniy-sharovykh-kranov-marshal/) explicitly specifies after climate designation: `0` mounting flange for actuator, `1` lever, `3` manual gearbox, `6` pneumatic actuator, `7` hydraulic actuator, `6(7)` pneumohydraulic, `9` electric, `10` T-key. MARSHAL `Ц` is full-bore, `2Ц` reduced, `ПФ` / `ФП` combinations must preserve mixed ends. Other digits represent DN/PN, not actuation.

ALSO family suffix `Р` generally refers to a version prepared **under gearbox/actuator**; this is neither a delivered manual-lever valve nor necessarily a valve with the gearbox installed. For explicit `КШ.Ф.Р.GAS` see [DN.ru catalogue](https://dn.ru/sharovyi-kran/gaz/flantcevyi-kran/standartnyi/also/kshfr01) and [ALSO GAS catalogue mirror](https://also.pro-solution.ru/wp-content/uploads/2020/03/katalog_ALSO_GAS.pdf). The full-bore `КШ.Ф.П.Р` execution is independently described in [ALSO manufacturer's model](https://alsoarm.ru/catalog/dlya-zhidkikh-sred/flantsevye/polnoprokhodnye-flantsevye-dlya-zhidkikh-sred/kran-sharovoy-also-dlya-zhidkikh-sred-flantsevyy-polnoprokhodnoy-pod-reduktor-dn-400-pn-16/).

## The 30 case decisions, one per current RAG Top-1

| # | Brand | Selected LD | Decision | Independent reason |
|---:|---|---:|---|---|
| 5 | MARSHAL | 15171 | REJECT | `2ЦП.01.0` **actuator-ready**; LD 15171 manual lever |
| 6 | MARSHAL | 1769 | REJECT | `2ЦФ.00.6(7)` **pneumohydraulic actuator**; LD 1769 manual |
| 10 | MARSHAL | 16350 | REJECT | `ЦФ.00.6` **pneumatic**; LD 16350 manual with flange kit (extra kit does not fix drive) |
| 11 | MARSHAL | 15177 | REJECT | `2ЦФ.01.6(7)` **pneumohydraulic**; LD 15177 manual |
| 12 | MARSHAL | 2723 | REJECT | `2ЦПФ.00.3` **combined welded/flanged** gearbox; LD 2723 is **flanged/flanged** gearbox (joint incompatible) |
| 14 | MARSHAL | 1499 | REJECT | `2ЦП.00.9` **electric actuation**; LD 1499 has manual gearbox |
| 24 | ALSO | 822 | REJECT | `КШ.ПР.GAS` actuator/gearbox-ready gas execution; LD 822 manual |
| 25 | ALSO | 2861 | REJECT | `КШ.ФПР.GAS` full-bore/under-drive; LD 2861 reduced-bore manual |
| 27 | MARSHAL | 16043 | REJECT | `ЦФ.01.7` **hydraulic**; LD 16043 manual |
| 29 | ALSO | 15489 | REVIEW | `КШ.Ф.RS.250.16-02`: source mapping lists gearbox, selected manual DN250/200. Need manufacturer's exact delivery/drive configuration |
| 34 | ALSO | 2472 | REVIEW | `КШ.ФЗ.RS.125.16-03`: neighbouring `КШ.Ф.З.RS` models are **full bore and for liquids**, matching LD 2472 DN125 PN16 stainless manual. Original GOLD is reduced; **strong additional-GOLD candidate**, but exact -03 official sheet not confirmed |
| 36 | ALSO | 15173 | REJECT | `КШ.ППТР.GAS` is a differentiated full-bore/actuator-ready gas execution; selected LD 15173 reduced-bore and manual. Confirm precise extra suffix details before suggesting alternative |
| 38 | MARSHAL | 356 | REJECT | `2ЦП.01.7` **hydraulic**; LD 356 manual gearbox |
| 41 | MARSHAL | 1523 | REJECT | `ЦП.00.6` **pneumatic**; LD 1523 manual gearbox |
| 43 | MARSHAL | 2078 | REJECT | `2ЦП.00.0` **actuator-ready**; LD 2078 manual |
| 44 | MARSHAL | 546 | REJECT | `2ЦФ.01.0` **actuator-ready**; LD 546 manual gearbox |
| 46 | MARSHAL | 17129 | REJECT | `2ЦФ.00.7` **hydraulic**; LD 17129 manual with flange kit |
| 49 | MARSHAL | 1242 | REJECT | `2ЦП.00.7` **hydraulic**; LD 1242 manual |
| 50 | ALSO | 1953 | REVIEW | `КШ.ФР.GAS.600.16-01` **under gearbox/actuator**; LD 1953 includes manual gearbox; business equivalence if supplied with extra gearbox requires confirmation |
| 55 | MARSHAL | 16999 | REJECT | `ЦП.01.0` **actuator-ready**; LD 16999 manual |
| 57 | MARSHAL | 16285 | REJECT | `2ЦР.01.7` **hydraulic**; LD 16285 manual threaded |
| 65 | MARSHAL | 2869 | REJECT | `2ЦП.00.6` **pneumatic**; LD 2869 manual gearbox |
| 66 | MARSHAL | 1809 | REJECT | `ЦП.00.6` **pneumatic**; LD 1809 manual |
| 74 | ALSO | **1532** | **APPROVE** | Exact competitor article `130501401MVA00000`: external product sheet says **heating water/oil, inner-inner threaded, reduced bore, manual, steel 20, DN50 PN40**. LD `13300509402MULD000000000` meets these; old GOLD only `Gas`, likely erroneous classification |
| 77 | ALSO | 16886 | REJECT | `КШ.ПТР.GAS` differs by drive-readiness; LD 16886 manual gas |
| 81 | MARSHAL | 15531 | REJECT | `ЦП.01.9` **electric**; LD 15531 manual |
| 90 | MARSHAL | 2197 | REJECT | `ЦП.00.7` **hydraulic**; LD 2197 manual (also check that `КШЦФИ` model truly has correct welded connection) |
| 92 | ALSO | 16315 | REJECT | `КШ.ФПР.040.16-01` full-bore/under drive; LD 16315 is reduced-bore manual, flange-kit does not fix bore |
| 99 | ALSO | 16302 | REJECT | `КШ.ФАР.125.25-02` special prepared-for-drive assembly; LD 16302 regular manual without independently confirmed equivalent execution |
| 100 | ALSO | 2058 | REJECT | `КШ.ФЗР.050.40-01` special full-bore, under-drive execution; LD 2058 reduced and manual, and short-body series differs (L is waived, drive/bore are not) |

### Additional proof, #74

- Exact ALSO vendor item [`130501401MVA00000`](https://res-36.ru/catalog/zapornaya-i-reguliruyushchaya-armatura/9338371-kran-sharovoy-muftovyy-standartnoprokhodnoy-dn-50-pn-40-st-20/): **«Среда применения: Теплосетевая вода, нефтепродукты»**, female/female thread, manual handle, 50/40, steel 20, reduced.
- LD [`13300509402MULD000000000`](https://s-teplovod.ru/catalog/krany-sharovye-stalnye-ld-/krany-sharovye-stalnye-ld-dlya-zhidkosti/kran-sharovyy-ld-muftovyy-kshtsm-st-20-du50-ru4-0-standartnoprokhodnoy/): female threaded, manual, DN50/40 PN40, steel 20, liquid.

### Remaining group and methodology

This report audits **only these 30 cases**. Other 32 E08 nonhits outside this group remain unchanged for separate checks. After approving #74, **39/100 = 39% offline hit-any** on this fixed DEV sample (from 34% original and 38% v2). This is **not a new live RAG run**, nor a claim about holdout/generalization.

**Intentional business omissions, reiterated:** construction length, and differences between named gas species, are deliberately ignored. **Gas-service vs liquid-service, DN/PN, ends, bore, steel and actual actuation are not ignored.**

**Additional catalog findings:** #34 likely reveals a *wrong original GOLD* (GOLD reduced while AL SO full series); #29 original mapping's gearbox may not follow from model text; several MARSHAL original GOLD `under electric drive` are not the same physical drive as manufacturer's explicit `.6/.7/.9` designations. These are data-quality issues independent of RAG quality, not grounds for automatic labels without true engineering evidence.
