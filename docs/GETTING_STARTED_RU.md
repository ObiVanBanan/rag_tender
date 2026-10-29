# Быстрый запуск RAG Tender

[← README](../README.md) · [API](API_RU.md) · [Эксплуатация](../PRODUCTION.md)

## 1. Предварительные условия

- Docker Engine / Docker Desktop и актуальный `docker compose` (override-файл использует Compose `!override`).
- Git LFS — Qdrant snapshot отслеживается в LFS.
- Ключ OpenAI для embeddings и ключ DeepSeek для query interpretation/rerank.
- LD-каталог `ld_products_full_nomenclature.csv` с исходной схемой, которую ожидает `load_products_from_csv`. Экспорт не входит в Git.
- Docker network `rag-observability-net`. Сами Grafana/Prometheus/Loki **не** входят в этот Compose; сеть служит для подключения отдельного стека.

> Полноценный старт невозможен без CSV и Qdrant snapshot; запуск только контейнеров API без этих данных не создаёт функциональный matcher. Платные запросы к провайдерам выполняются только при обращении к API или при явных live smoke-тестах.

## 2. Получить код и данные

```bash
git clone https://github.com/ObiVanBanan/rag_trend.git
cd rag_trend
git switch codex/catalog-first-technical-compatibility-v2
git lfs install
git lfs pull
```

Для Windows/PowerShell:

```powershell
git clone https://github.com/ObiVanBanan/rag_trend.git
Set-Location rag_trend
git switch codex/catalog-first-technical-compatibility-v2
git lfs install
git lfs pull
Copy-Item .env.example .env
```

Для Linux/macOS: `cp .env.example .env`.

Убедитесь, что `qdrant/steel_products_active.snapshot` — настоящий бинарный snapshot, а не LFS pointer. Поместите `ld_products_full_nomenclature.csv` в корень проекта или укажите его реальный путь через `PRODUCT_CSV_HOST_PATH` в `.env`.

## 3. Настроить секреты

В `.env` заполните:

```dotenv
OPENAI_API_KEY=<your-openai-key>
DEEPSEEK_API_KEY=<your-deepseek-key>
POSTGRES_PASSWORD=<unique-random-password>
API_DATABASE_USER=rag_tender_api
API_DATABASE_PASSWORD=<different-unique-random-password>
API_AUTH_TOKEN=<different-random-token-at-least-32-chars>
WEB_SEARCH_ENABLED=false
```

Генерация одного секрета (запустите отдельно **три раза**):

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`POSTGRES_PASSWORD` нужен миграциям/администрированию; API использует отдельную роль `API_DATABASE_USER`. Не используйте одно значение для двух ролей. Поле `DATABASE_URL` в Compose собирается из `API_DATABASE_PASSWORD`; для ручного запуска вне Compose задайте корректную строку подключения отдельно. Если пароль содержит зарезервированные URL-символы, используйте URL-кодирование в строке подключения или генерируйте URL-безопасный пароль.

Web search оставлен выключенным: в текущей оценённой конфигурации runtime-web не использовался, а внешнее обогащение не должно молча менять поведение.

## 4. Поднять сервис

```bash
docker network inspect rag-observability-net >/dev/null 2>&1 || docker network create rag-observability-net
docker compose config --quiet
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8000/health/live
curl http://127.0.0.1:8000/health/ready
```

Windows PowerShell:

```powershell
docker network inspect rag-observability-net
# Если сеть отсутствует:
docker network create rag-observability-net
docker compose config --quiet
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

Запуск с `.env.example` предполагает `API_PORT=8000`. Compose автоматически читает `docker-compose.override.yml`; этот файл меняет некоторые порты и конфигурацию для совместного размещения с мониторингом. При изменении `API_PORT` проверьте итоговую конфигурацию через `docker compose config`.

После старта: Swagger UI — `http://127.0.0.1:8000/docs`. Health checks публичные; matching и metrics требуют Bearer token. **Не публикуйте порт API напрямую**: для удалённого доступа необходимы TLS reverse proxy, сетевые ограничения и управление секретами.

## 5. Первый запрос

```bash
export API_AUTH_TOKEN="значение-из-вашего-.env"
curl -sS -X POST http://127.0.0.1:8000/v1/match \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"products":["Кран шаровой стальной Ду50 Ру16 для воды"]}'
```

PowerShell:

```powershell
$env:API_AUTH_TOKEN = "значение-из-вашего-.env"
$headers = @{ Authorization = "Bearer $env:API_AUTH_TOKEN" }
$body = @{ products = @("Кран шаровой стальной Ду50 Ру16 для воды") } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/match -Headers $headers -ContentType "application/json" -Body $body
```

Ответ содержит статус по каждой позиции, название и артикул LD при подборе, `request_id` и `latency_ms`. Для строгой ручной проверки используйте `/v1/shortlist`.

## 6. Тесты без облачных ключей

```bash
uv sync --locked --extra test
uv run python -m pytest -q tests
```

Полный набор тестов предназначен для локального/CI окружения; некоторые интеграционные скрипты отдельно требуют PostgreSQL/провайдеров. Конкретная зелёная проверка должна выполняться на коммите, который планируется релизить.

## 7. Если что-то не работает

| Симптом | Что проверить |
|---|---|
| `qdrant-init` не восстановил индекс | `git lfs pull`; настоящий файл `qdrant/steel_products_active.snapshot`; `docker compose logs qdrant-init` |
| API не проходит readiness | `docker compose logs api db-migrate`; Qdrant collection, SQL миграции и CSV |
| Нет файла каталога | Путь `PRODUCT_CSV_HOST_PATH` на хосте, bind mount, схема CSV |
| `401 unauthorized` | `Authorization: Bearer ...`, токен в `.env` |
| `429 MATCHER_BUSY` | В текущем процессе уже выполняется batch; см. `API_MAX_INFLIGHT_BATCHES` |
| `429 HOURLY_ITEM_LIMIT_REACHED` | Достигнут лимит попыток позиций за 60 минут в этом процессе |
| `NOT_FOUND` на известную позицию | Это не обязательно «нет аналога»: проверить входные атрибуты, кандидатов через shortlist, снапшот и source catalog |
| Проблемы с Qdrant/моделями | `docker compose logs api qdrant` и correlation по `X-Request-ID` |

**Обновление БД:** перед миграцией живой БД сохраните и протестируйте backup. Миграция `0002` меняет primary key исторических строк на `history_id`, сохраняя клиентский `request_id` как неуникальную корреляцию. Подробности — [PRODUCTION.md](../PRODUCTION.md).

**Секреты:** не публикуйте `.env`, реальные логи с токенами, базы с запросами клиентов и данные GOLD/holdout. Если секрет попал в историю Git, удаление в новом коммите недостаточно — его нужно отозвать/перевыпустить.

