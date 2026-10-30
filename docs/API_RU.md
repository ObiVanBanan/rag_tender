# HTTP API

[← README](../README.md) · [Запуск](GETTING_STARTED_RU.md)

Базовый адрес при обычном `docker compose` (включая `docker-compose.override.yml`): `http://127.0.0.1:8002`. OpenAPI: `/openapi.json` и `/docs`. Для удалённого доступа используйте HTTPS reverse proxy.

## Аутентификация и общие правила

- `GET /health/live` и `GET /health/ready` — публичные проверки; ready возвращает `503` при недоступности зависимостей.
- `POST /v1/match`, `POST /v1/shortlist` и `GET /metrics` — Bearer авторизация. При отсутствующем/неверном токене `401`.
- Заголовок `X-Request-ID` может быть передан клиентом; иначе API генерирует значение. Это **не** уникальный ключ записи истории.
- Ограничения размера: от 1 до `API_MAX_BATCH_SIZE` элементов (по умолчанию 100), каждая строка до 4000 символов. Для превышения числа элементов API возвращает `413`; пустое/неверное тело валидируется как `422`.
- Оба match-маршрута делят process-local admission: `429` (`MATCHER_BUSY` или `HOURLY_ITEM_LIMIT_REACHED`) и `Retry-After`. Лимит не является денежной гарантией.

## `POST /v1/match`

**Тело:**

```json
{
  "products": [
    "Кран шаровой стальной Ду50 Ру16 для воды",
    "Фланец стальной плоский Ду100 Ру16"
  ]
}
```

**Форма ответа (значения условные, не результат системы):**

```json
{
  "request_id": "example-request-id",
  "results": [
    {
      "input": "Кран шаровой стальной Ду50 Ру16 для воды",
      "status": "NOT_FOUND",
      "matched_name": null,
      "matched_article": null,
      "score": null,
      "confidence": null,
      "error_code": null
    }
  ],
  "latency_ms": 0.0
}
```

Массив `results` соответствует каждой входной строке. `status`: `MATCHED` / `NOT_FOUND` / `ERROR`. Для `MATCHED` возвращаются `matched_name` и `matched_article` (если в каталоге), а также скоринг. `score` — поисковый сигнал, `confidence` — заявленная оценка reranker, не калиброванная вероятность.

**Важно:** отдельный статус `INSUFFICIENT_PARAMETERS` и формат top-10 выбора **не входят** в контракт этой production-ветки.

## `POST /v1/shortlist`

**Тело:**

```json
{
  "queries": [
    {
      "query": "Кран шаровой стальной Ду50 Ру16 для газа",
      "working_medium": "GAS"
    }
  ],
  "max_candidates": 10
}
```

`working_medium` принимает `GAS`, `LIQUID` или `UNKNOWN`. Если строка явно говорит «для газа» или «для воды», значение поля должно соответствовать тексту, иначе запрос отклоняется валидацией.

Ответ содержит `request_id`, `latency_ms` и `results`. Каждый элемент имеет:

| Поле | Значение |
|---|---|
| `input`, `requested_medium` | Исходный запрос и заданная среда |
| `status` | `REVIEW_REQUIRED`, `NO_CANDIDATES` или `ERROR` |
| `decision` | Всегда `REVIEW_REQUIRED` |
| `human_review_required` / `automatic_approval` | `true` / `false` |
| `candidates` | Кандидаты для проверки, с LD ID, артикулом, атрибутами, retrieval и reranker signals |
| `blocked_candidates` | Отдельные кандидаты с конфликтом рабочей среды |
| `candidate_count` / `blocked_candidate_count` / `candidate_pool_truncated` | Диагностика полноты shortlist |

Каждый кандидат содержит `working_medium` (requested/catalog classification/disposition), `gas_certification=UNVERIFIED` и признаки обязательного человеческого ревью. В частности, `UNKNOWN` и `BOTH` не доказывают допуск для газа. `max_candidates` в диапазоне 1–20.

## Диагностика

```bash
curl http://127.0.0.1:8002/health/ready
curl -H "Authorization: Bearer $API_AUTH_TOKEN" http://127.0.0.1:8002/metrics
```

Коды `429` указывают на ограничение дорогостоящих вызовов до обращения к провайдерам, но процессные лимиты сбрасываются после рестарта. Подробности по history, миграциям и live smoke: [PRODUCTION.md](../PRODUCTION.md).

Для интеграций не полагайтесь на конкретное значение `confidence` или абсолютное `latency_ms` из иллюстраций — нужны ваши реальные замеры.

