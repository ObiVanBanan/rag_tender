# Competitor catalog sources

This directory contains source metadata and data-driven catalog schemas for
`CompetitorResolver`.

## V2 rule

The resolver must distinguish a **product family** from an **exact product
variant**.

Examples:

- `MARSHAL 11с67п` -> FAMILY_LEVEL
- `MARSHAL 11с67п 2ЦП.01.0.025.100` -> exact variant candidate
- `TEMPER 29420125` -> exact article

Family pages may describe nomenclature and family-level properties, but they
must not create an exact ProductRecord by themselves.

## TEMPER catalog schema

TEMPER is intentionally represented as a manufacturer catalog schema instead
of hand-entered benchmark SKUs.

The official catalog uses structured article numbers:

```
<series><material-code><DN>
```

Examples:

- `29420125` -> series 294, material code 20, DN125
- `29266025` -> series 292, material code 66, DN25

The registry stores series-level rules (joining type, bore type, PN schedule)
and material-code mappings. `CatalogRegistry` combines those official
nomenclature rules with the exact article to build an exact product profile.

This means new articles from a covered series can be resolved without adding
one JSON record per SKU.

## Sources

- MARSHAL official catalog index:
  https://lztamarshal.ru/support/katalogi/
- ALSO official GAS catalog:
  https://alsoarm.ru/catalog/dlya-gazoobraznykh-sred-seriya-gas/
- TEMPER official catalog PDF:
  https://temper.ru/docs/af4af09985ca8f3a1cd3ae88d0d5f3ae.pdf
- BROEN official documentation:
  https://www.broen.com/documentation/district-energy/brochures-and-documentation/

## Safety rules

1. GOLD / acceptable LD mappings must never be stored here.
2. Family-only identity must never be persisted as an exact product.
3. Exact ProductRecords require a full article/variant identity.
4. Neighbor SKU evidence cannot populate exact-product facts.
5. Runtime KB v2 uses a separate table from v1 so legacy family-collapsed rows
   cannot affect resolver-v2.
6. Adding a generic official catalog/schema is allowed; adding exact products
   only because they appeared in the benchmark is not.

## Catalog-first safety and coverage audit (2026-10-21)

The official nomenclature rules are the authority for decoded model attributes;
the LLM only helps interpret the request. Exact *syntactic* model identity is not
proof that a specific manufactured variant exists. Never create a GOLD mapping
or an LD article from a source manufacturer's identity.

- **MARSHAL:** the official marking specification confirms drive codes
  0/1/3/6/7/6(7)/9/10. Mixed ПФ/ФП joining is preserved. Special
  deliveries, gas certifications and exact manufacturer SKU existence remain
  unverified unless supported by an exact product document.
- **ALSO:** confirmed explicit full-bore under-reducer Ф.П.Р and ФПР
  designations. Gearbox *ready* does not mean the gearbox is supplied.
  Unknown and З-series bore remain unverified. Several RS, short-body and
  special executions still require exact datasheets before auto-approval.
- **TEMPER:** local schemas cover 282/284/287/292/294/299 and
  special MAX 980/982/983/990/992/993, but control, exact product existence
  and some PN ranges are not known from the article alone. Do not invent
  unknown fields, especially PN for MAX 992 DN300+.

Verified schema-derived facts are promoted into the same hard constraints as
explicit query facts. If these two sources disagree, matching is rejected
with VERIFIED_CATALOG_CONFLICT. SUPPORTED-only web claims are not promoted.
The existing runtime avoids web calls on resolved catalog hits; missing
catalog facts must be completed through a separate source-backed catalog
acquisition/review process, not guessed by the model. Results still need
frozen100 E2E validation before production promotion.

Official references:
- MARSHAL https://lztamarshal.ru/support/tekhnicheskaya-dokumentatsiya/struktura-oboznacheniy-sharovykh-kranov-marshal/
- ALSO https://alsoarm.ru/catalog/dlya-zhidkikh-sred/flantsevye/polnoprokhodnye-flantsevye-dlya-zhidkikh-sred/kran-sharovoy-also-dlya-zhidkikh-sred-flantsevyy-polnoprokhodnoy-pod-reduktor-dn-400-pn-16/
- TEMPER https://temper.ru/catalog/1-stalnaa-armatura-sarovye-krany-dla-zidkih-sred?per-page=30&view=full
