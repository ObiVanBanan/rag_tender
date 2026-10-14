# Почему перестали проходить реальные тендеры: A/B до оптимизации 100 → сегодня

**Эксперимент**: `codex/tender-regression-ab-v1` (draft PR #17), основан на узких фланцевых изменениях draft PR #16. Никаких изменений matcher в PR #17. Не сливать до живой валидации.

## Найденные факты (не гипотезы)

Сохранённый исторический отчет [`data/harness_baseline.json` от 2026-09-09](https://github.com/ObiVanBanan/rag_trend/blob/5768c4591c9a92cc3a9c33338a163b83a15d81d5/data/harness_baseline.json) действительно содержит **11 из нынешних 20** реальных тендерных строк. Итог на этих 11: 9 `PASS`, 1 `FAIL_WRONG_NOT_FOUND` (#033), 1 `FAIL_UNKNOWN_PRODUCT_DATA` (#036). Из 9 `PASS` часть зачтена по полной технической совместимости, а не точному ID из неполного списка human positives.

**Исторический отчет за 9 сентября — доказательство старого поведения, но не кодовый baseline A/B.** Для A/B используем [`336d7c08`](https://github.com/ObiVanBanan/rag_trend/commit/336d7c08cbface23afb0cbd6ae83736e294d870f) от 24 сентября — последний commit исходной линии до изменений retrieval под competitor100. Родитель первого такого изменения [`d7a64f00`](https://github.com/ObiVanBanan/rag_trend/commit/d7a64f00aa8731e8a61445655437dbf855bd80b8) (27 сентября) ровно `336d7c08`. В этом baseline Query Interpreter и жесткая проверка уже **есть**. Правила намеренного отказа по недостатку характеристик остаются в текущем matcher без изменений.

9 остальных строк `EXTENDED`, в т. ч. стальные фланцы под ПНД, исторически подтверждались другим способом: просмотр каталога + ChatGPT с экспертной проверкой. В найденном `harness_baseline.json` они **не выполнялись в E2E**. Нельзя утверждать, что все они раньше автоматически подбирались успешно.

Коммиты возможных причин расхождения:
- [`6eb0603` (14 сен)](https://github.com/ObiVanBanan/rag_trend/commit/6eb0603905d1954d622550b65ba24a368bfa7700): query gate, теперь может вернуть `NOT_FOUND` до поиска.
- [`464482a` (14 сен)](https://github.com/ObiVanBanan/rag_trend/commit/464482ae74590a0c754b3f75096dc40a042ac83e): строгие hard constraints.
- [`3752f85` (24 сен)](https://github.com/ObiVanBanan/rag_trend/commit/3752f854633aa34a4050a0cf3dda41c3103a3ca9): `canonical_material(query)` делает ошибочно распознанный ПНД жёстким условием.
- [`54e7c44` (13 окт)](https://github.com/ObiVanBanan/rag_trend/commit/54e7c44dc4f89073ce116df8598ae239d4866481): технический prefilter широкого RRF-пула.

Последние три — **гипотезы о причинах конкретных ошибок**, пока стадийные trace не получены; сообщение коммита само по себе не доказывает вину.

## Порядок правильного эксперимента

Не сравнивать сохранённые 24/30 от 9 сентября с 1/20 от 14 октября: это разный протокол, разные выборки и разное время. Вместо этого:

1. `tender20`: один и тот же список 20 verified строк на **пред-оптимизационном matcher 24 сентября (`336d7c08`)**, на исходном **текущем demo**, затем на экспериментальном **flange-fix**. Сравнить exact positive Top-1, возможные альтернативы, intentional sparse `NOT_FOUND` и этапы `QUERY_GATE / RETRIEVAL_MISS / TECHNICAL_PREFILTER_DROP / HARD_FILTER_DROP / RERANK_NOT_SELECTED`.
2. `frozen100`: **только текущий demo vs кандидат**, ровно одни и те же 100 примеров из frozen-популяции, seed 53; запретить ухудшение exact known-positive Top-1 или потерю любого ранее успешного кейса. Пред-оптимизационный matcher не является текущим frozen100 baseline.
3. Оценить альтернативные LD по фактическим обязательным характеристикам, чтобы не путать `OTHER_LD_REQUIRES_REVIEW` с доказанным неверным аналогом. `known_positive_ids_exhaustive=false` — положительные метки неполны.
4. Только после live метрик переносить подтвержденные улучшения в рабочую демо-ветку.

## Однокомандный запуск на машине с Qdrant и ключами

Потребуется **один** полный CSV LD (тот же, что у сервера), **один** живой Qdrant alias и **один** набор ключей/моделей для обеих версий.

```bash
git fetch origin
git checkout codex/tender-regression-ab-v1
uv sync --locked --extra test

# Файл .env содержит OPENAI_API_KEY, DEEPSEEK_API_KEY,
# QDRANT_URL и QDRANT_COLLECTION_ALIAS.
# QDRANT_URL должен быть доступен ИЗ HOST, не docker-only hostname.
uv run python scripts/run_evolution_ab.py \
  --cohort tender20 \
  --csv "$(pwd)/ld_products_full_nomenclature.csv" \
  --env-file .env \
  --run-live
```

Скрипт сам создаёт изолированные git worktree на коде до оптимизации 100 (`336d7c08`) и на текущей demo-ветке; исполняет `scripts/match_batch.py` без Postgres и без публичного API. Набор tender20 берётся из зафиксированного коммита с GOLD [`e1661896`](https://github.com/ObiVanBanan/rag_trend/commit/e1661896e8d0c7fbb18c02adb4abb9a1d93b4d2f) (9 сентября), так как старая comparator-ветка этого датасета не содержит. Новые изменения находятся в текущем checkout. GOLD IDs передаются **только** offline evaluator, LLM видит только входные строки и кандидатов.

Сначала проверь `.tmp/evolution-ab/tender20/report.private.json`: сколько `QUERY_GATE` с `INTENTIONAL_SPARSE_REFUSAL`, сколько `HARD_FILTER_DROP` (материал/присоединение), сколько `RERANK_NOT_SELECTED`. Прогон старого алгоритма на текущем индексе **не является точной реконструкцией среды 24 сентября** — это контролируемый эксперимент только над разницей алгоритмов.

Далее, если по 20 появились проверенные улучшения:

```bash
uv run python scripts/run_evolution_ab.py \
  --cohort frozen100 \
  --csv "$(pwd)/ld_products_full_nomenclature.csv" \
  --env-file .env \
  --run-live
```

Или `--cohort both`, если хочешь запустить всё сразу. Прогон 20 делает до 60 matcher запросов (старый+текущий+кандидат), frozen100 — до 200; каждый matcher запрос вызывает embeddings и DeepSeek. Без `--run-live` скрипт ничего не запустит.

**ACCEPT только при** `frozen100_acceptable=true` и отсутствии regression cases. При любом потерянном ранее успешном кейсе скрипт завершится с отказом. Даже это не подтверждает причинную устойчивость при дрейфе LLM: для окончательной промоции подозрительные случаи нужно повторить и технически адъюдицировать.

## Где артефакты

Локально, не в Git:
- `.tmp/evolution-ab/environment_fingerprint.json`: SHA CSV, SHA ревизий, модели и Qdrant alias, без API ключей.
- `.tmp/evolution-ab/tender20/{historic,current,candidate}.raw.private.json`: сырые ответы и trace.
- `.tmp/evolution-ab/tender20/report.private.json`: per-case причины, метрики, переходы.
- `.tmp/evolution-ab/frozen100/report.private.json`: сравнение и строгий acceptance verdict.

**Не коммитить артефакты**, содержащие GOLD, query/candidate IDs и сырые ответы. Не копировать Gold ID в правила matcher, prompt или каталог. Тесты инструмента не используют реальные Gold.
