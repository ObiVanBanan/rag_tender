# Roadmap и критерии готовности

[← README](../README.md) · [Качество](QUALITY_RU.md)

Состояние по осмотру кода ветки `codex/catalog-first-technical-compatibility-v2` на **29.10.2026**. Это не обязательства по датам.

## Реализовано в выбранной интеграционной ветке

- FastAPI `/v1/match` и `/v1/shortlist`; проверка среды и review-only contract.
- Catalog-first competitor resolver + SQLite KB и JSON catalog registry.
- Hybrid retrieval, technical prefilter, DeepSeek reranker, optional web search.
- PostgreSQL history с `history_id`, migrations, bearer auth, health, metrics.
- Compose и отдельные операционные smoke-скрипты; регрессионные тесты.

## Отдельные/незавершённые направления

| Приоритет | Инициатива | Критерий приёмки |
|---|---|---|
| P0 | Интеграция и ревью stacked PR #29 → #31 → #32 | Один чистый релизный baseline, полный CI и smoke |
| P0 | Безопасность публикации | Secret scan по текущему дереву и истории, rotation подозрительных секретов, проверка происхождения данных |
| P0 | Live end-to-end | Переход через реальные OpenAI/DeepSeek/Qdrant/Postgres, корректная обработка ошибок и лимитов |
| P0 | Независимая оценка | Зафиксированный holdout; повторяемые metrics + статистика причин несовпадений |
| P1 | Свести business UI | Разбор атрибутов, top-10 для выбора, ручная коррекция, добавление одного товара в текущую партию |
| P1 | CSV-first → RAG fallback | Единый поддерживаемый контракт и тест на промах CSV; не смешивать с CSV для BM25 |
| P1 | Полная история UI | Сохранение и просмотр **снимка запроса и ответа**, не только названия товара |
| P1 | Визуализация статистики | Top-1, pool recall, ошибки по техническим атрибутам, latency и стоимость |
| P1 | Безопасная публикация | TLS proxy, provider spend cap, секреты вне репо, мониторинг и backup/restore |
| P2 | Deployment/scale | Нагрузочные тесты, общая quota при multi-worker, отдельный deploy наблюдаемости |

Работы по UI/CSV-first существуют в отдельных PR/ветках и **не считаются внедрёнными** в эту ветку до фактического объединения и тестирования. Ссылки для навигации: [PR #15 business demo](https://github.com/ObiVanBanan/rag_trend/pull/15), [PR #27 CSV-first](https://github.com/ObiVanBanan/rag_trend/pull/27), [PR #32 verified catalog constraints](https://github.com/ObiVanBanan/rag_trend/pull/32).

## Release gates

### Для Technical Preview

- [ ] Выбрать целевую базовую ветку и закрыть stacked merge-conflicts.
- [ ] Пройти тесты `uv run python -m pytest -q tests` на финальном commit.
- [ ] Пройти Compose config и build на том же commit.
- [ ] Поднять стенд с лицензированным LD CSV, materialized LFS snapshot и API-ключами.
- [ ] Выполнить `scripts/smoke_production_e2e.py` и проверить два отдельных history snapshots на одинаковом `X-Request-ID`.
- [ ] Пройти security + data provenance audit, зафиксировать границы доступа.
- [ ] Опубликовать точные условия измерения качества и limitations.

### Для production/закупочной интеграции

- [ ] Инженерный gate и источник документов для критичных сред / сертификатов.
- [ ] Проверенный независимый holdout и регрессионный набор по DN/PN/connection/medium/control.
- [ ] Backup + rehearsal миграций `0001`/`0002` на копии БД, rollback plan.
- [ ] TLS, network rules, rate/budget caps по внешним провайдерам, секреты через секрет-хранилище.
- [ ] Наблюдаемость на целевом окружении и измеренные стоимость, p50/p95.
- [ ] Уточнить лицензию репозитория и права на каталожные данные.

Все пункты по умолчанию **не отмечены**: документационный PR не выполняет такие проверки автоматически.

