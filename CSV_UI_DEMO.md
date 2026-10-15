# Бизнес-демо 16 октября: CSV → RAG

## Каскадная логика

- Сначала **все три CSV**. Проверяем артикул и обязательные технические
  ограничения. При наличии подходящей пары показываем её без вызова RAG.
- Если CSV не дал ни одного прошедшего проверку аналога — автоматически
  запускаем **исходный RAG** (Qdrant dense + BM25 + LLM-интерпретация/реранкер).
- Если обязательных параметров недостаточно, не идём к RAG:
  просим уточнение, чтобы не обходить защиту.
- Если RAG не смог выполниться из-за сервиса, возвращается ошибка, а не
  ложный «аналога нет».
- Оба источника используют **один и тот же UI** на `/demo`. Под каждой
  позицией отображается «Источник: CSV» или «Источник: RAG».
- Топ-10, выбор другого кандидата, история со снимками ответов,
  редактирование и точечное добавление позиции сохранены.

## Запуск каскадного режима в Windows PowerShell

```powershell
git fetch origin
git switch experiment/csv-mapping-ui-demo
git pull --ff-only

# Если не делали ранее, извлеките архив с тремя маппингами в корень репозитория:
Expand-Archive .\rag_tender_csv_mapping_data.zip -DestinationPath . -Force

# Полный чемпионский Qdrant snapshot хранится в Git LFS:
git lfs pull

if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Отредактируйте .env: OPENAI_API_KEY, DEEPSEEK_API_KEY,
# PUBLIC_DEMO_PASSWORD, PUBLIC_DEMO_ADMIN_PASSWORD
# Укажите корректный PRODUCT_CSV_HOST_PATH (полный LD-каталог CSV).

docker compose -f docker-compose.hybrid-demo.yml up -d --build
```

Откройте **http://localhost:8001/demo**. Войдите логином
`PUBLIC_DEMO_USERNAME` (по умолчанию `demo`) и паролем из
`PUBLIC_DEMO_PASSWORD`. Статистика: `/demo/stats` с отдельной
администраторской учётной записью.

Проверить запуск:

```powershell
curl.exe http://localhost:8001/health/ready
docker compose -f docker-compose.hybrid-demo.yml ps
docker compose -f docker-compose.hybrid-demo.yml logs --tail=100 api
```

**Важное про пути:** `PRODUCT_CSV_HOST_PATH` — файл LD-каталога,
ранее использовавшийся RAG; маппинги CSV не заменяют этот каталог.
Проверьте, что `qdrant/steel_products_active.snapshot` — настоящий
snapshot, а не файл-указатель Git LFS. Если Qdrant не поднялся,
используйте резервный CSV-only режим ниже.

**Не запускайте одновременно** `docker-compose.csv-demo.yml` и
`docker-compose.hybrid-demo.yml`: оба по умолчанию публикуют порт 8001.
Остановить отдельный CSV-only режим можно:
`docker compose -f docker-compose.csv-demo.yml down`.

## Сценарий показа

1. Введите `1184399` — ожидается поиск в CSV (показать источник).
2. Введите `SVB-0001-000025` — второй пример CSV.
3. Введите **фланец из вашего работающего прежнего RAG**, отсутствующий
   в маппингах. Результат, если найден, будет с источником RAG.
4. Откройте кандидатов, выберите альтернативу, добавьте позицию,
   проверьте снимок ответа в истории.
5. Проверьте безопасность: `Кран шаровый 11Б27П Ду20 Ру16` должен
   запросить среду и тип/размер резьбы вместо автоматического выбора.

`MATCH_BACKEND=hybrid` (задано в гибридном Compose) — основной режим показа.
`MATCH_BACKEND=csv_mapping` (задано в отдельном CSV Compose) — резерв.
`MATCH_BACKEND=catalog` — исходный чистый RAG, не меняется.

## Резерв: локальная CSV-only версия

Если облачные ключи, LD-каталог или Qdrant недоступны:

```powershell
docker compose -f docker-compose.hybrid-demo.yml down
docker compose -f docker-compose.csv-demo.yml up -d --build
```

CSV-only обрабатывает только товары с готовыми соответствиями в маппингах.
Без RAG неизвестный артикул даст `NOT_FOUND`.

## Ограничения качества

- CSV-маппинги **не** подтверждают инженерную взаимозаменяемость.
- RAG-подбор также требует технической проверки. Наличие результата
  не означает 100% точности.
- Три файла маппингов не находятся в публичной Git-ветке и исключены
  через `.gitignore`. Это **входные данные**, не независимый GOLD.
- Проверки в CI используют синтетические примеры и заглушку RAG.
  Настоящий Qdrant+LLM e2e требует вашего LD-каталога, снимка индекса
  и ключей и в CI не выполняется.
- Общая ветка от `codex/business-demo-oct16`; старый UI и исходный
  `codex/business-demo-oct16` не изменены.
