# Contributing to RAG Tender

[README](README.md) · [Архитектура](docs/ARCHITECTURE_RU.md) · [Качество](docs/QUALITY_RU.md)

## Рабочий процесс

1. Создайте рабочую ветку от актуального `main`. Ветка содержит catalog-first runtime и бизнес-демо; экспериментальные PR не включайте автоматически.
2. Зафиксируйте цель, тесты и возможные изменения контракта API в PR.
3. Установите зависимости: `uv sync --locked --extra test`.
4. Запустите `uv run python -m pytest -q tests` и узкие тесты затронутых модулей.
5. Для изменений Compose/миграций выполните `docker compose config` с локальными секретами и операторские smoke-тесты.
6. Для изменений ранжирования разделяйте DEV tuning, validation и holdout. Не используйте GOLD/acceptable ID в resolver или prompt. Не публикуйте GOLD-bearing trace.
7. Указывайте, какие проверки **не** выполнены (нет API-ключей, Qdrant, сети, CI и т. п.).

## Куда вносить изменения

- `domain/` — техническая совместимость и типы; никаких сетевых вызовов.
- `application/` — orchestration/use cases; через порты.
- `infrastructure/` и адаптеры — внешние зависимости.
- `api.py` — основной HTTP контракт и авторизация; `business_demo.py` / `business_demo*.html` — интерфейс и human-review API; `demo_feedback.py` — история действий.
- `production.py` — composition root.
- `tests/` — регрессии для исправлений DN/PN/материалов/среды/присоединений.

Критичные safety checks должны работать при неизвестных атрибутах без догадки «подходит». Нельзя менять политику gas↔liquid или вводить автоapproval незаметно.

## Чего не коммитить

- `.env`, токены, сертификаты, реальные DSN/пароли.
- Приватные LD/контрагентские каталоги без разрешения на публикацию.
- GOLD/holdout, ответы эталонного mapping с допустимыми LD ID, полные traces с конфиденциальными данными.
- Логи с клиентскими запросами, API payload с персональными или коммерческими данными.

По вопросам уязвимостей используйте [SECURITY.md](SECURITY.md), не публичный PR.

