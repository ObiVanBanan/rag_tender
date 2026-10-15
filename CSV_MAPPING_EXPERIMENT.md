# CSV mapping experiment (not validated production logic)

The branch `experiment/csv-mapping-backend` adds an opt-in backend which uses
three precomputed **competitor → LD** mapping CSVs instead of official competitor
catalog profiles. `MATCH_BACKEND=catalog` remains the default.

## Data placement

Place these files in `data/csv_mappings/`:

- `competitor_ld_mapping.csv`
- `butterfly_mapping_results.csv`
- `mapping_results.csv`

The original CSVs are not included in the Git branch: they were uploaded in the
conversation and must be copied locally (the companion sandbox archive contains
them in the correct directory). The format is unchanged; note that the butterfly
file uses `;` and UTF-8 BOM, whereas the other two use commas.

## Run

```bash
# No Qdrant or model/API keys are needed for CSV-only matching.
python scripts/csv_mapping_search.py '1184399' --limit 10
python scripts/eval_csv_mapping_smoke.py --sample 200

docker compose -f docker-compose.csv.yml up -d --build
curl -s http://localhost:8000/health/ready
curl -s -X POST http://localhost:8000/v1/match \
  -H 'Content-Type: application/json' \
  -d '{"products":["1184399","PALUR-ZD-3EX-DN1000-PN16-1N-FL-EL-U1-(ST/KR)-(KR/M.KR.G)","Кран 11Б27П Ду20 Ру16"]}'
```

`CSV_MAPPING_DIR` controls where data is loaded; `MATCH_BACKEND=csv_mapping`
selects this backend on the regular production runtime (the dedicated Docker
compose file selects it automatically). The existing API response contract is
unchanged; the first candidate is returned as `matched_*`. Use the standalone
script to inspect up to ten alternatives. This branch **must not be promoted**
without explicit ranking and business approval for ambiguous alternatives.

## Safety / limits

- A source article or whole normalized source name must be present. No
  similarity-only auto-accept or fallback to an unknown competitor family.
- Explicit DN, PN, connection, control, medium, material and thread orientation
  are checked against source-side facts when possible; missing facts are not
  treated as proven. Unsupported technical constraints (temperature,
  installation length, seals, exact bore, etc.) are **not fully validated**.
- Material grade `P235GH` and obvious standard/full-bore vs regulating mismatches
  are blocked for automation pending engineering review.
- Mapping scores are ignored as confidence. In `mapping_results.csv` many rows
  have `match_score > match_max`, so the scales are not calibrated.
- A mapping can yield multiple LD alternatives. The API's current first-choice
  behavior is a compatibility experiment, **not a safe auto-substitution policy**.
- Direction is normalized on loading: `mapping_results.csv` and
  `butterfly_mapping_results.csv` encode `LD → competitor`; this backend
  reverses them to `competitor → LD`.
- Butterfly rows do not contain LD's full product title/URL. We return the
  supplied LD marking as the display title rather than inventing a title.
- CSV-only exact identity matching does not replace a complete LD product
  corpus for free-form tenders. Unseen identities return NOT_FOUND.

## Evaluation (no GOLD leakage)

`eval_csv_mapping_smoke.py` deliberately compares lookups against the **same
CSV rows that built the index**. It verifies loading, identity coverage and
negative DN gates. Its top1/top10 scores are **not accuracy estimates**.

An honest catalog-vs-CSV benchmark requires an **independent frozen** set of
competitor tender queries with human-reviewed acceptable LD substitutions,
which are absent from all three loaded mapping CSVs. Sample by grouped
competitor source identities, hold out any samples also used to construct CSV
mappings, and report `top1`, `hit@10`, `wrong_not_found`, `false_match`,
`unknown`, latency and cost for both backends. Existing benchmark
`eval_competitor_analogs.py` derives expected answers from `mapping_results.csv`
and must **not** be reused to claim CSV-backend generalization.
