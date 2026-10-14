# Flange rescue v1: изолированный патч с проверкой frozen-100

**Статус:** эксперимент, не promoted. Ветка `codex/flange-rescue-guarded-v1` ответвлена от бизнес-демо `codex/business-demo-oct16`. Пока frozen-100 не пройден, рабочую демо-ветку и champion не меняем.

## Зачем

Исходный прогон `demo20_results.json`: exact top1 1/20, `WRONG_NOT_FOUND=12`, `WRONG_PRODUCT=7`. Среди отказов есть четыре запроса **стальной фланец DNx под втулку ПНД DNy**, а также плоский приварной фланец. Гипотеза: неверная привязка двух DN, материала и конструкции присоединения отбрасывает LD до реранкера.

Не исправляем `WRONG_PRODUCT=7` без trace и экспертной проверки альтернатив.

## Что меняется (ограничено фланцами)

- Ранее `explicit_dn_from_query()` возвращал `None` при двух DN. Теперь только при явной конструкции `Фланец DN X под втулку ПНД DN Y` возвращает DN фланца X, а отдельно в `flange_sleeve_dn_pair()` сохраняет Y. Другие запросы с двумя DN по-прежнему неоднозначны.
- Если стальной фланец описан через сопряжённую полиэтиленовую втулку, `body_material=steel`, а не `polyethylene`. Фильтры/LLM интерпретация корректируются только для этой конструкции.
- В старой exp4 `приварной` трактовался как `flanged` глобально. В новой реализации такое правило применяется **только к фланцу**, у приварного шарового крана остаётся `welded`.
- Правила отказа при недостатке атрибутов не менялись. `фильтр Ду50`, `кран шаровый Ду150` по-прежнему отклоняются.

## Локальная проверка CI (без облачных моделей)

```bash
uv run --extra test python -m pytest -q \
  tests/test_flange_rescue_guarded.py \
  tests/test_query_constraints.py \
  tests/test_compare_eval_reports.py \
  tests/test_replay_frozen100_api.py
```

Проверяется также, что сохранённая когорта E08 seed53 (100 строк) не содержит целевой фразы «фланец» и новый двух-DN parser для неё не срабатывает. **Это ещё не гарантия равной Top-1 метрики**, потому что поиск/LLM и среда исполнения могут отличаться.

## Обязательный E2E-эксперимент 100: base против candidate

Запускайте две версии последовательно на **том же сервере** с **одинаковыми** CSV, Qdrant snapshot, DeepSeek model/API, embedding model, `.env`, и seed53. Не отправляйте известные GOLD id в API.

Удобно сделать две worktree-копии рядом (в исходном git-клоне):

```bash
git fetch origin
git worktree add --detach ../rag-before origin/codex/business-demo-oct16
git worktree add --detach ../rag-after origin/codex/flange-rescue-guarded-v1
```

В обе копии поместить одинаковый `.env` и выполнить `git lfs pull`. В `.env` для обеих указать **одинаковый абсолютный** `PRODUCT_CSV_HOST_PATH=/абсолютный/путь/к/ld_products_full_nomenclature.csv`, `API_PUBLISH_BIND=127.0.0.1:8000` и `PUBLIC_DEMO_PASSWORD`. Обе версии используют один Compose project `rag-tender-guard` **последовательно**, чтобы volumes и Qdrant index не менялись. Не запускать их одновременно с одинаковыми `container_name`.

Один раз подготовить runner:

```bash
cd ../rag-after
uv sync --locked --extra test
read -rsp "PUBLIC_DEMO_PASSWORD: " PUBLIC_DEMO_PASSWORD && export PUBLIC_DEMO_PASSWORD && echo
```

Запустить старую версию:

```bash
cd ../rag-before
docker compose -p rag-tender-guard -f docker-compose.yml up -d --build
curl -f http://127.0.0.1:8000/health/ready
cd ../rag-after
uv run python scripts/replay_frozen100_api.py --out .tmp/frozen100_before.json
```

Заменить только версию приложения, не удаляя тома:

```bash
cd ../rag-before
docker compose -p rag-tender-guard -f docker-compose.yml down
cd ../rag-after
docker compose -p rag-tender-guard -f docker-compose.yml up -d --build
curl -f http://127.0.0.1:8000/health/ready
uv run python scripts/replay_frozen100_api.py --out .tmp/frozen100_after.json
```

Проверить метрику, состав cohort и неизменность GOLD:

```bash
uv run python scripts/compare_eval_reports.py \
  --baseline .tmp/frozen100_before.json \
  --candidate .tmp/frozen100_after.json \
  --require-no-case-regressions
```

Скрипт возвращает ненулевой exit code, если понизилась Top-1, появились потерянные ранее проходившие строки (при strict-флаге), изменилась выборка или GOLD. Подробности — локально в `.tmp/frozen100_comparison.json`, без отправки меток/LD ID в GitHub.

## Повторить старые 20 на candidate

```bash
git fetch origin prod/rag-tender-exp4
uv run python scripts/export_demo20_cases.py
uv run python scripts/demo_recheck.py \
  --cases .tmp/demo20_verified.json \
  --out .tmp/demo20_after.json
```

Скрипт `demo_recheck.py` также читает `PUBLIC_DEMO_PASSWORD` из переменной среды для авторизации. Сравнить с исходным результатом 1/20, отдельно `WRONG_NOT_FOUND` на фланцах. Проверить реальные кандидаты: новый MATCHED ещё не доказывает техническую корректность.

**ACCEPT** только при: сохранённой/улучшенной frozen-100 top1, отсутствии ранее проходивших регрессий (strict gate), отсутствии изменения политики sparse queries и положительном приросте проверенных фланцев 20-case. Иначе **REJECT** без слияния.

Узкие фиксированные изменения и тесты не гарантируют качество: без живого Qdrant/провайдеров эта ветка остаётся неподтверждённой.
