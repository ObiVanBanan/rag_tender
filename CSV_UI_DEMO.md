# Бизнес-демо: CSV-маппинги в существующем UI

Изолированная ветка от `codex/business-demo-oct16`. UI не заменён: используются
`/demo`, `/v1/demo/match`, `/v1/demo/correct`,
`/v1/demo/append`, `/v1/demo/decision` и `/demo/stats`.
Поиск работает на локальных CSV; Qdrant, LLM и внешний интернет **не нужны**
для самого сопоставления. PostgreSQL нужен для истории решений/статистики.

## Запуск (Windows PowerShell)

```powershell
git fetch origin
git switch --track origin/experiment/csv-mapping-ui-demo
# Скачанный отдельно архив rag_tender_csv_mapping_data.zip лежит в корне репозитория
Expand-Archive .\rag_tender_csv_mapping_data.zip -DestinationPath . -Force

if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# В .env задайте PUBLIC_DEMO_PASSWORD и PUBLIC_DEMO_ADMIN_PASSWORD
docker compose -f docker-compose.csv-demo.yml up -d --build
```

Откройте **http://localhost:8001/demo** (доступ по `PUBLIC_DEMO_USERNAME`,
по умолчанию `demo`, и заданному `PUBLIC_DEMO_PASSWORD`).

**http://localhost:8001/demo/stats** — статистика с отдельными
`PUBLIC_DEMO_ADMIN_USERNAME` / `PUBLIC_DEMO_ADMIN_PASSWORD`.

Для проверки доступности API (отвечает без авторизации):

```powershell
curl.exe http://localhost:8001/health/ready
```

Удобнее проверять поиск и историю непосредственно в веб-интерфейсе.

Поддерживаемые демонстрационные артикулы:
- стальной кран: `1184399`
- латунный кран: `SVB-0001-000025`
- дисковый затвор: `PALUR-ZD-3EX-DN1000-PN16-1N-FL-EL-U1-(ST/KR)-(KR/M.KR.G)`

Не используйте для демонстрации фланцы без конкурирующей пары из CSV:
большинство запросов на фланцы не покрыты этими файлами.
Узнать покрытие можно только поиском по конкретному запросу.

## Границы достоверности

- CSV — предварительно построенные соответствия, а не подтверждённые инженером GOLD.
- В режиме CSV показаны кандидаты с меткой источника: ТОП-10 в существующем UI,
  первый предварительный кандидат и возможность выбора другого.
- Строго отсекаются конфликтующие DN, PN, присоединения, известные ошибки
  исполнения и расхождения явных параметров. Неизвестное не доказывает
  взаимозаменяемость. Температуру, длину, уплотнения, стандарты и детали
  исполнения следует проверять человеком.
- Кнопки исправления параметров и «Добавить позицию» сохраняют артикул
  конкурента и не пересчитывают предыдущие позиции; полный снимок ответа
  сохраняется в истории браузера/системе обратной связи.
- Backend `MATCH_BACKEND=catalog` по умолчанию НЕ тронут. CSV включён только
  в отдельном `docker-compose.csv-demo.yml` через `MATCH_BACKEND=csv_mapping`.
- Источники CSV не закоммичены и исключены через `.gitignore`. Их нельзя
  использовать одновременно как поисковую базу и как независимый эталон.
- Smoke-покрытие по данным тех же CSV **не является независимой точностью**.

## Проверки

```powershell
python -m pytest -q tests/test_csv_demo_integration.py
docker compose -f docker-compose.csv-demo.yml config
docker compose -f docker-compose.csv-demo.yml ps
```

Контроль перед показом: открыть `/demo`, ввести три примера, посмотреть
топ-10, выбрать другой вариант и проверить историю; добавить новую позицию;
проверить `11Б27П Ду20 Ру16` (должен запросить параметры среды и резьбы).
В случае недоступности CSV-демо исходная
`codex/business-demo-oct16` остаётся неизменённой.
