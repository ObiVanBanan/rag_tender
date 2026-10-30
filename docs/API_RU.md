# HTTP API

[← README](../README.md) · [Запуск](GETTING_STARTED_RU.md)

Базовый адрес при обычном `docker compose` (включая `docker-compose.override.yml`): `http://127.0.0.1:8002`. OpenAPI: `/openapi.json` и `/docs`. Для удалённого доступа используйте HTTPS reverse proxy.

## Аутентификация и общие правила

- `GET /health/live` и `GET /health/ready` — публичные проверки; ready возвращает `503` при недоступности зависимостей.
- `POST /v1/match`, `POST /v1/shortlist` и `GET /metrics` — Bearer авторизация. При отсутствующем/неверном токене `401`.
- Браузерное демо `/demo` и `/v1/demo/*` использует отдельную HTTP Basic авторизацию (пользователь `PUBLIC_DEMO_USERNAME`, пароль `PUBLIC_DEMO_PASSWORD`); `/demo/stats` и `/v1/demo/stats` требуют отдельную администраторскую пару. В production без пароля демо закрыто. HTTP Basic допускается только за HTTPS reverse proxy.
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

**Важно:** `INSUFFICIENT_PARAMETERS`, top-10 и действия пользователя являются частью отдельного **демо-контракта** `/v1/demo/*`, а не ответом `/v1/match`.

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

## Бизнес-интерфейс и review API

- `GET /demo` — HTML-интерфейс для инженера с импортом текстовых строк, просмотром кандидатов и сохранением локальных слепков запроса и ответа.
- `POST /v1/demo/match` — `{"products":["Фланец стальной DN50 PN16"]}`. Возвращает `request_id`, одноразовый `review_token`, `results`, список реально найденных кандидатов (до 10) и объяснения технической проверки. Лимит по умолчанию — 10 строк, длина строки — до 2000 символов.
- `POST /v1/demo/correct` — пересчитывает **одну позицию** после правки `changes`. Нужны `request_id`, `review_token`, `item_index`, `revision`. Повторный запрос использует ту же catalog-first цепочку и общий admission budget.
- `POST /v1/demo/decision` — фиксирует `ACCEPTED`, `REJECTED` или `SELECTED_OTHER`; для выбора альтернативы также передаётся `selected_ld_id`. Несовпадение технических требований или неизвестные данные требуют отдельных признаков ручного подтверждения, не считаются автоматическим approval.
- `GET /demo/stats` и `GET /v1/demo/stats?days=30` — приватная статистика на PostgreSQL с отдельными правами администратора.

Основной Bearer API и HTML-демо имеют разные контракты и логины. `review_token` не следует записывать в URL или `localStorage`: история браузера содержит только снимки для чтения, без сессионного доступа на изменение. Подробный сценарий: [DEMO_RU.md](DEMO_RU.md).

## Диагностика

```bash
curl http://127.0.0.1:8002/health/ready
curl -H "Authorization: Bearer $API_AUTH_TOKEN" http://127.0.0.1:8002/metrics
```

Коды `429` указывают на ограничение дорогостоящих вызовов до обращения к провайдерам, но процессные лимиты сбрасываются после рестарта. Подробности по history, миграциям и live smoke: [PRODUCTION.md](../PRODUCTION.md).

Для интеграций не полагайтесь на конкретное значение `confidence` или абсолютное `latency_ms` из иллюстраций — нужны ваши реальные замеры.

