# Roadmap и критерии готовности

[← README](../README.md) · [Качество](QUALITY_RU.md)

Состояние интеграционной ветки на **30.10.2026**. Это не обязательства по датам; фактическая эксплуатационная готовность зависит от сквозных проверок.

## Реализовано в выбранной интеграционной ветке

- FastAPI `/v1/match` и `/v1/shortlist`; проверка среды и review-only contract.
- Catalog-first competitor resolver + SQLite KB и JSON catalog registry.
- Hybrid retrieval, technical prefilter, DeepSeek reranker, optional web search.
- PostgreSQL history с `history_id`, migrations, bearer auth, health, metrics.
- Compose и отдельные операционные smoke-скрипты; регрессионные тесты.
- Бизнес-демо `/demo`: top-10 кандидатов, редактирование технических параметров, выбор человеком, браузерные слепки и серверные feedback events; `/demo/stats` с графиками.

## Отдельные/незавершённые направления

| Приоритет | Инициатива | Критерий приёмки |
|---|---|---|
| P0 | Live E2E на объединённом `main` | Зафиксировать PASS на реальных разрешённых данных, Qdrant и действующих LLM с корректными отказами |
| P0 | Безопасность публикации | Secret scan по текущему дереву и истории, rotation подозрительных секретов, проверка происхождения данных |
| P0 | Live end-to-end | Переход через реальные OpenAI/DeepSeek/Qdrant/Postgres, корректная обработка ошибок и лимитов |
| P0 | Независимая оценка | Зафиксированный holdout; повторяемые metrics + статистика причин несовпадений |
| P1 | Проверка интеграции business UI | Live-демо на реальных данных, тест совместимости со всеми catalog-first ограничениями и доступами |
| P1 | CSV-first → RAG fallback | Единый поддерживаемый контракт и тест на промах CSV; не смешивать с CSV для BM25 |
| P1 | История UI между устройствами | Браузерные слепки реализованы; для синхронизации потребуется учётная запись и безопасное серверное хранение |
| P1 | Визуализация статистики | Top-1, pool recall, ошибки по техническим атрибутам, latency и стоимость |
| P1 | Безопасная публикация | TLS proxy, provider spend cap, секреты вне репо, мониторинг и backup/restore |
| P2 | Deployment/scale | Нагрузочные тесты, общая quota при multi-worker, отдельный deploy наблюдаемости |

UI перенесён из [PR #22](https://github.com/ObiVanBanan/rag_trend/pull/22); CSV-first из PR #27 намеренно не перенесён. Перенос исходного кода ещё не подтверждает успешный live E2E. Ссылки для навигации: [PR #15 business demo](https://github.com/ObiVanBanan/rag_trend/pull/15), [PR #27 CSV-first](https://github.com/ObiVanBanan/rag_trend/pull/27), [PR #32 verified catalog constraints](https://github.com/ObiVanBanan/rag_trend/pull/32).

## Release gates

### Для Technical Preview

- [x] Объединить catalog-first архитектуру и бизнес-демо в `main` ([PR #35](https://github.com/ObiVanBanan/rag_trend/pull/35), [PR #36](https://github.com/ObiVanBanan/rag_trend/pull/36)).
- [x] Выполнить CI на интегрированном `main`: 267 passed, 1 skipped ([run 40999898702](https://github.com/ObiVanBanan/rag_trend/actions/runs/40999898702)).
- [x] Проверить Compose config, PostgreSQL migration smoke и Docker build в том же CI.
- [ ] Поднять стенд с лицензированным LD CSV, materialized LFS snapshot и API-ключами.
- [ ] Выполнить `scripts/smoke_production_e2e.py` и проверить два отдельных history snapshots на одинаковом `X-Request-ID`.
- [ ] Пройти security + data provenance audit, зафиксировать границы доступа.
- [ ] Опубликовать точные условия измерения качества и limitations.

### Для production/закупочной интеграции

- [ ] Инженерный gate и источник документов для критичных сред / сертификатов.
- [ ] Проверенный независимый holdout и регрессионный набор по DN/PN/connection/medium/control.
- [ ] Backup + rehearsal миграций `0001`/`0002`/`0003` на копии БД, rollback plan.
- [ ] TLS, network rules, rate/budget caps по внешним провайдерам, секреты через секрет-хранилище.
- [ ] Наблюдаемость на целевом окружении и измеренные стоимость, p50/p95.
- [ ] Уточнить лицензию репозитория и права на каталожные данные.

Пройденные проверки отмечены отдельно; наличие CI не заменяет реальный E2E, аудит каталогов и промышленную приёмку.

