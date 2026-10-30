# Архив ранней проектной документации

Это **исторические** документы и планы прежних этапов RAG Tender, перемещённые из корня репозитория. Они не определяют текущую архитектуру, API, требования безопасности или готовность к релизу. Внутренние ссылки и упомянутые ветки/коммиты могут быть устаревшими.

Для актуального состояния используйте [README](../../README.md), [архитектуру](../ARCHITECTURE_RU.md), [API](../API_RU.md), [бизнес-демо](../DEMO_RU.md) и [план работ](../ROADMAP_RU.md).

- [Исходное ТЗ на MVP](legacy/tz-mvp.md)
- [Research report для раннего analyst-shortlist](legacy/research_report-shortlist.md)
- [Архитектурный ADR по shortlist](legacy/shortlist-adr.md)
- [Промежуточная архитектура рефакторинга](legacy/architecture-refactoring.md)
- [План реализации shortlist](legacy/shortlist-implementation-plan.md)

Экспериментальные результаты и трассы остаются отдельно в `docs/EXPERIMENTS.md` и `docs/experiments/`. Шесть частей встроенного benchmark в `data/competitor_analog_hit_any_min_v1.parts/` **не являются временными файлами**: их считывает `scripts/eval_competitor_analogs.py`. Не удаляйте их при уборке.
