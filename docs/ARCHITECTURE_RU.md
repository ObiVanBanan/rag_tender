# Архитектура RAG Tender

[← README](../README.md) · [API](API_RU.md) · [Design notes](../design/architecture.md)

## Системный контекст

```mermaid
flowchart TB
    C["Клиент: ERP / скрипт / инженер"] -->|HTTPS через reverse proxy| API["FastAPI /v1/match, /v1/shortlist"]
    API --> ADM["Process-local admission gate"]
    ADM --> APP["Application use cases"]
    APP --> PREP["QueryPreparationService"]
    PREP --> INT["DeepSeek query interpreter"]
    PREP --> RES["CompetitorResolver"]
    RES --> REG["Catalog registry JSON"]
    RES --> KB[("SQLite competitor KB")]
    PREP --> RET["HybridCandidateSearchService"]
    RET --> EMB["OpenAI embeddings"]
    RET --> Q[("Qdrant: dense")]
    RET --> BM["BM25: LD CSV in memory"]
    RET --> PREF["RRF + technical prefilter"]
    PREF --> RER["DeepSeek reranker"]
    RER --> POL["Domain compatibility policy"]
    POL --> API
    API --> HIST["RequestHistoryRecorder"]
    HIST --> PG[("PostgreSQL: immutable snapshots")]
    API --> MET["Prometheus metrics / structured logs"]
```

Граница системы — API. Мониторинг Grafana/Prometheus/Loki работает **внешним стеком** через общую Docker network, а не создаётся основным Compose. В коде остаётся опциональный web lookup (MCP), но рекомендуемая оценённая конфигурация имеет `WEB_SEARCH_ENABLED=false`.

## Обработка запроса

```mermaid
sequenceDiagram
    autonumber
    actor Client as Клиент
    participant API as FastAPI
    participant Gate as Admission
    participant Prep as Query prep
    participant Search as Dense + BM25 + RRF
    participant Rank as Prefilter + rerank
    participant Policy as Domain policy
    participant DB as PostgreSQL
    Client->>API: POST /v1/match {products:[...]}
    API->>API: Bearer, schema, batch limits
    API->>Gate: reserve(item count)
    alt нет квоты / занят matcher
      Gate-->>API: 429 + Retry-After
      API-->>Client: отказ до платных вызовов
    else есть квота
      loop каждый товар последовательно
        Gate->>Prep: исходная строка
        Prep->>Prep: параметры + идентичность + catalog facts
        Prep->>Search: канонический поисковый запрос
        Search->>Rank: кандидаты + атрибуты
        Rank->>Policy: проверить hard/soft ограничения
        Policy-->>API: matched / not found / error
      end
      API->>DB: сохранить request + response snapshot
      API-->>Client: results, request_id, latency_ms
    end
```

`/v1/shortlist` использует тот же matcher, но возвращает кандидатов для ревью, в том числе `blocked_candidates` при явной несовместимости рабочей среды. Это не approval workflow и не технический сертификат.

## Логические слои

| Слой | Папка / ключевые файлы | Ответственность |
|---|---|---|
| HTTP / transport | `src/nomenclature_matcher/api.py` | Входные модели, bearer auth, коды HTTP, health, metrics |
| Application | `application/{matching,query_preparation,hybrid_candidate_search,candidate_selection,candidate_reranking,shortlist,...}.py` | Сценарии, управление конвейером, history recorder, admission |
| Domain | `domain/{product,constraints,medium,competitor,query_signals}.py` | Товарные факты, технические ограничения, UNKNOWN, проверка среды |
| Infrastructure | `infrastructure/{postgres_history,competitor_knowledge_store,competitor_catalog_registry,...}.py` | Доступ к хранилищам и внешним источникам |
| Composition | `production.py` | Внедрение зависимостей, жизненный цикл ресурсов |
| Adapters | `embeddings.py`, `qdrant_store.py`, `bm25_store.py`, `reranker.py` | Сторонние API и поиск |
| Runtime | `docker-compose.yml`, `Dockerfile`, `migrations/` | Контейнеры, SQL миграции, права, готовность |

## Почему такой конвейер

1. **Catalog-first / identity guard.** Обозначение производителя и конкретное исполнение рассматриваются как источник возможных ограничений. Нельзя подменять неизвестный вариант «похожим семейством» без evidence.
2. **Hybrid retrieval.** Dense покрывает смысловые вариации; BM25 сохраняет лексические совпадения по обозначениям и параметрам. Списки объединяются через RRF.
3. **Technical prefilter.** Жёсткие известные ограничения и мягкие признаки учитываются до окончательного top-20, снижая риск потери подходящего кандидата на раннем отсечении.
4. **Rerank + review.** LLM помогает расставлять кандидатов, но не объявляет их сертифицированными. Пустые или конфликтующие факты требуют ручной проверки.
5. **Auditability.** JSON snapshot запроса и ответа сохраняется с отдельным уникальным `history_id`. Клиентский `X-Request-ID` — корреляционный ID и может повторяться.

## Границы и незакрытые риски

- Текущая реализация создаёт BM25 по LD CSV в памяти. Масштабирование Uvicorn workers дублирует объём; лимит запросов/час — process-local, не распределённый.
- Если SQL history недоступна, readiness не пройдёт; проблемы persistence логируются, но ответ matching может быть сформирован отдельно.
- Не реализованы гарантированный денежный budget провайдеров, многоарендность и RBAC.
- Для реального production необходимы TLS, проверенный backup/restore, secret scanning, отдельные provider spend caps и end-to-end проверка на целевом окружении.
- Режимы UI и CSV-first живут в других ветках; они **не входят** в этот deployable runtime.

Подробный рефакторинг и портовая архитектура — в [design/architecture.md](../design/architecture.md). Логи/метрики — в [OBSERVABILITY.md](../OBSERVABILITY.md).


## Откуда берутся характеристики конкурентов

```mermaid
flowchart TD
    U["Тендер: производитель + модель/артикул + DN/PN"] --> X["Identity extraction: точная модель или только семейство?"]
    X -->|Нет точного исполнения| F["FAMILY_LEVEL / UNKNOWN — без выдумывания SKU"]
    X -->|Точное обозначение| R["CompetitorResolver"]
    C["Официальные каталоги MARSHAL / ALSO / TEMPER"] --> S["Curated catalog registry / designation schemas"]
    S --> R
    K[("SQLite KB: источник, provenance, exact identity")] --> R
    R --> P["Canonical product facts: DN, PN, material, joining, bore, control, medium"]
    P --> V{"Данные VERIFIED и нет противоречий?"}
    V -->|Конфликт с запросом| B["Fail closed: VERIFIED_CATALOG_CONFLICT / review"]
    V -->|Нет подтверждения| H["UNKNOWN / ручная проверка"]
    V -->|Да| Q["Hard constraints для LD candidate search"]
    Q --> D["Qdrant dense + LD CSV BM25 + RRF"]
    D --> L["DeepSeek reranking + compatibility policy"]
    L --> O["LD shortlist / API response / обязательная инженерная проверка"]
```

**Приоритет источников:** подтверждённый каталог точного исполнения и явно заданные требования тендера важнее предположений LLM. Если они конфликтуют, система не должна выбирать «похожий» продукт. Шаблон обозначения может декодировать атрибуты модели, но само наличие синтаксически корректного артикула **не подтверждает существование SKU** и допуски для газа. Каталожные исходники и ограничения по производителям — [data/competitor_catalogs/README.md](../data/competitor_catalogs/README.md).

**Важное различие:** производственные каталоги конкурентов нужны для *понимания исходного товара*. Отдельный LD CSV и индекс Qdrant нужны для *поиска аналога в целевом каталоге*. Никакие GOLD-метки не должны попадать в runtime resolver.
