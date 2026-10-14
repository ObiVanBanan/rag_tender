# Демо подбора тендерных аналогов LD (16 октября 2026)

Демо добавлено к существующей production ветке `codex/competitor-resolver-v2`; алгоритм поиска и публичный `POST /v1/match` не меняются.

## Запуск

1. Выполнить `git lfs pull`, заполнить `.env` (OPENAI_API_KEY, DEEPSEEK_API_KEY, POSTGRES_PASSWORD), проверить наличие индекса Qdrant.
2. Выполнить `docker compose up -d --build`.
3. Проверить `http://localhost:8000/health/ready`; открыть `http://localhost:8000/demo`.
4. Swagger: `http://localhost:8000/docs`, бизнес endpoint: `POST /v1/demo/match`, вход `{"products":["Кран шаровой Ду50 Ру16"]}`.
5. Фокус показа: оригинальный запрос → извлечённые DN/PN/материал/присоединение → рекомендованные LD → отдельно кандидаты, требующие проверки → технический статус и задержка.

## Метрики и честные оговорки

- Поле `retrieved_count` — размер выдачи после поиска, а не точность.
- `recommended_count` — число выбранных ранжировщиком LD, а не доказательство совместимости.
- `score` — поисковый балл; `llm_confidence` — утверждение модели; **ни одно не является калиброванной вероятностью верного сопоставления**.
- `NOT_FOUND` означает, что pipeline не подтвердил совпадение, но не доказывает отсутствие товара во всём каталоге.
- Старый отчёт `data/harness_gold_eval.json` ветки `prod/rag-tender-exp4`: **16/19 (84,2%)** на 2026-09-08. Не выдавать за свежую оценку 20/100.
- Не путать `data/eval_queries_v2.json` (11 кейсов) с **оригинальной двадцаткой** `data/tender_queries_v1_harness_cases.json` (11 CORE + 9 EXTENDED) из ветки `prod/rag-tender-exp4`. Её mapping хранится в `data/tender_queries_v1_canonical_labels.json` там же; 20 подтверждённых положительных меток **неисчерпывающие**. Их попадание — нижняя граница технической полноты, не готовая точность.
- Необходимо перезапустить **оба** набора: 20 и 100 кейсов на выбранном коммите и фиксированном каталоге/моделях. Раздельно считать exact top1 / strict constraint pass, false match, wrong NOT_FOUND и latency p50/p95. Unreviewed и SILVER не подменять human-GOLD.

## Повторный прогон оригинальных 20 кейсов

```bash
git fetch origin prod/rag-tender-exp4
python scripts/export_demo20_cases.py
python scripts/demo_recheck.py --cases .tmp/demo20_verified.json --out .tmp/demo20_results.json
```

Оригинальные GOLD-артикулы не должны попадать в LLM контекст, retrieval или в публичные данные демо. Скрипт отправляет в API только `query`; сравнение с эталоном выполняется локально после ответа.

## Проверка

`uv run pytest -q tests/test_business_demo.py tests/test_production_api.py`

Демо endpoint предназначен для локального/закрытого показа, без авторизации его нельзя публично выставлять в интернет. Проверка работающих ключей, Docker, Qdrant, PostgreSQL, провайдеров и E2E делается на машине владельца окружения.
