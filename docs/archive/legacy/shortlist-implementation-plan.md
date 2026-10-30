# План реализации: доменный analyst shortlist для competitor matching

## Общая информация
- **Тип:** Архитектурный рефакторинг и API-фича
- **Связанные артефакты:** `research_report.md`, `design/adr.md`, `docs/PRODUCT_DECISION_E08_SEED53.md`
- **Краткое описание:** Выделить доменную политику рабочей среды и отдельный use case, который публикует до 20 ранжированных кандидатов с данными для аудита. Явный конфликт газа и жидкости блокируется; каждый результат требует проверки человеком.
- **Общая оценка:** 4-5 инженерных дней до релизной готовности с миграциями, тестами и live-интеграционной проверкой.

## Дорожная карта (Milestones)

### Milestone 1: Доменная политика и use case (готово по коду; тестовый gate открыт)
- [x] Task 1.1: Описать границы текущего кода и выбрать безопасный контракт
  - Файлы: `research_report.md`, `design/adr.md`
  - DoD: зафиксированы pipeline, ограничения каталога, API-контракт и fail-closed правила
  - Оценка: 1 час
  - Зависимости: Нет
- [x] Task 1.2: Вынести категорию рабочей среды и сбор shortlist в отдельный модуль
  - Файлы: `src/nomenclature_matcher/domain/medium.py`, `src/nomenclature_matcher/application/shortlist.py`
  - DoD: классификатор чистый и детерминированный; explicit conflict разделён с review-required данными; список ограничен 20 элементами
  - Оценка: 3 часа
  - Зависимости: Task 1.1

### Milestone 2: API интеграция и наблюдаемость (код готов; проверка gate открыта)
- [x] Task 2.1: Добавить независимый `/v1/shortlist` контракт
  - Файлы: `src/nomenclature_matcher/api.py`, `src/nomenclature_matcher/application/matching.py`, `src/nomenclature_matcher/application/shortlist.py`
  - DoD: старый `/v1/match` не меняет схему; shortlist сохраняется через текущую историю; ошибки item-level не раскрывают exception text
  - Оценка: 3 часа
  - Зависимости: Task 1.2
- [ ] Task 2.2: Проверить код-ревью и безопасность ответа
  - Файлы: `design/adr.md`, `plan/implementation_plan.md`
  - DoD: отсутствуют автоматическое одобрение, незаявленная совместимость, секреты и лишние вызовы модели; API и persistence проверены интеграционно
  - Оценка: 2 часа
  - Зависимости: Task 2.1

### Milestone 3: Production boundaries and deployment security (частично выполнено)
- [x] Task 3.1: Отделить application use cases и PostgreSQL adapter от composition root
  - Файлы: `src/nomenclature_matcher/application/`, `src/nomenclature_matcher/infrastructure/postgres_history.py`, `src/nomenclature_matcher/production.py`
  - DoD: API использует application matcher port; persistence имеет отдельный adapter; старые импорты остаются совместимыми
  - Оценка: 3 часа
  - Зависимости: Task 2.1
- [x] Task 3.2: Закрыть production API bearer-auth и убрать слабые Compose credentials
  - Файлы: `src/nomenclature_matcher/api.py`, `src/nomenclature_matcher/settings.py`, `src/nomenclature_matcher/production.py`, `.env.example`, `docker-compose.yml`, `docker-compose.override.yml`, `PRODUCTION.md`
  - DoD: production fail-fast без 32+ символов API токена; auth на operational routes; Compose требует заданные секреты и публикует базовый API только на loopback
  - Оценка: 3 часа
  - Зависимости: Task 1.1
- [x] Task 3.3: Проверить ошибки аутентификации, history миграции, старый API контракт и shortlist на интеграционном стенде
  - Файлы: `tests/test_production_api.py`, `tests/test_query_constraints.py`, `PRODUCTION.md`
  - DoD: HTTP tests cover `/v1/match`, oversized batches, bounded query length, `/v1/shortlist` review-only contract, bearer rejection/acceptance, request history, and health. Migration applied to clean and legacy schemas. Current full suite passes with 199 tests, including recorder persistence and telemetry failure behavior.
  - Оценка: 4 часа
  - Зависимости: Task 3.1, Task 3.2

### Milestone 4: Decompose the matcher facade and competitor resolver (код выполнен; 199 tests passed)
- [x] Task 4.1: Вынести candidate selection, second-chance retrieval, reranking и гибридный candidate search в application services
  - Файлы: `src/nomenclature_matcher/matcher.py`, `src/nomenclature_matcher/application/`, `src/nomenclature_matcher/domain/product.py`, `src/nomenclature_matcher/domain/constraints.py`, `src/nomenclature_matcher/query_constraints.py`
  - DoD: legacy методы `NomenclatureMatcher` делегируют services; matcher/retriever/reranker зависимости описаны ports; LDProduct и правила совместимости принадлежат domain; старые импорты query_constraints работают через compatibility facade; hard gate и порядок rerank сохранены
  - Оценка: 1 день
  - Зависимости: Task 2.1
- [x] Task 4.2: Вынести query interpretation, competitor enrichment и retrieval-plan orchestration из `NomenclatureMatcher`
  - Файлы: `src/nomenclature_matcher/matcher.py`, `src/nomenclature_matcher/application/`, `src/nomenclature_matcher/infrastructure/`
  - DoD: фасад делегирует подготовку запроса и enrichment сервису; сохранены identity gate, web fallback и trace contract. 185 tests outside `test_production_api.py` plus 3 non-`TestClient` production API tests pass; two HTTP integration tests remain blocked by sandbox socketpair creation.
  - Оценка: 2 дня
  - Зависимости: Task 3.3, Task 4.1
- [x] Task 4.3: Проверить и завершить versioned migration для request-history DDL
  - Файлы: `src/nomenclature_matcher/infrastructure/`, `src/nomenclature_matcher/production.py`, новая директория миграций
  - DoD: migration service applies schema to a clean database and a legacy database with UUID request IDs and an existing view; startup only checks migration version; Postgres adapter open/ping/close passed against live isolated PostgreSQL.
  - Оценка: 1 день
  - Зависимости: Task 3.3
- [x] Task 4.4: Ввести typed runtime lifecycle ports для matcher clients и persistence
  - Файлы: `src/nomenclature_matcher/production.py`, `src/nomenclature_matcher/application/ports.py`, `src/nomenclature_matcher/infrastructure/`
  - DoD: runtime uses Protocol ports for matcher, history, catalog readiness, telemetry and resource scope; `ExitStack` shutdown is covered for idempotent close.
  - Оценка: 1 день
  - Зависимости: Task 4.2
- [x] Task 4.5: Разнести competitor resolver по домену, application и infrastructure
  - Файлы: `src/nomenclature_matcher/domain/competitor.py`, `src/nomenclature_matcher/application/competitor_resolver.py`, `src/nomenclature_matcher/infrastructure/competitor_*.py`, compatibility facade `src/nomenclature_matcher/competitor_resolver.py`
  - DoD: приложение использует store/catalog ports; SQLite и JSON loading создаются в composition root; legacy settings-based import сохранён; architecture tests запрещают application->infrastructure и domain->outer-layer imports.
  - Проверка: полный suite — 199 passed after adding request-history recorder tests.

## Зависимости между задачами
- Task 1.1 → Task 1.2 → Task 2.1 → Task 2.2 → Task 3.1/3.2 → Task 3.3 → Task 4.1/4.2 → Task 4.3/4.4.

## Риски и заметки
- Среда в каталоге свободным текстом; варианты значений по полному каталогу ещё не инвентаризированы.
- Сертификация отсутствует как структурированные данные и остаётся `UNVERIFIED`.
- Bearer auth добавлен, но остаётся общий shared secret без ролей/ротации; rate limit и abuse controls нужны до internet exposure.
- Python compile/import, the 199-test full suite, OpenAPI contract, `uv lock --check`, and `docker compose config --quiet` pass. A locked production image built and ran as UID 10001; API import and the locked DuckDuckGo CLI smoke passed. Isolated PostgreSQL migration smokes passed for clean and legacy schemas; the API's non-superuser role opened/pinged/inserted/closed with DDL denied. Full-stack acceptance with project-owned provider credentials, live Qdrant, and deployment settings remains outstanding because the current `.env` has no required runtime credentials.
- Docker build now installs locked third-party dependencies in a source-independent layer; verified the first full dependency install and a second build with all layers cached, then verified a source-only rebuild reuses dependency layers and completes app packaging in seconds.
- API root filesystem is read-only with tmpfs, all capabilities dropped, and `no-new-privileges`. A read-only metadata check found the existing KB volume root-owned; a networkless one-shot `CAP_CHOWN` init service was added. It was tested against a temporary root-owned SQLite volume, then verified writable by UID 10001 without altering the existing volume.
- Checkout detached; создание ветки заблокировано правами на общий `.git/refs`, поэтому локальные изменения остаются в текущем worktree.
