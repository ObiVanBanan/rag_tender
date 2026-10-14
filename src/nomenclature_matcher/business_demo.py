"""Business-friendly DTO and UI around the existing, unchanged tender matcher.

Never interpret retrieval rank, LLM confidence or MATCHED share as accuracy.
"""
from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

from .observability import get_request_id

router = APIRouter(tags=["Бизнес-демо"])

FIELDS = {
    "product_type": "Тип изделия",
    "dn": "Номинальный диаметр",
    "pn_min_mpa": "Номинальное давление",
    "joining_type": "Присоединение",
    "thread_type": "Тип резьбы",
    "working_medium": "Рабочая среда",
    "valve_type": "Исполнение",
    "valve_designation": "Обозначение",
    "body_material": "Материал корпуса",
    "body_material_grade": "Марка материала",
    "bore_type": "Тип прохода",
    "control": "Управление",
}
VALUES = {
    "ball_valve": "Шаровой кран", "butterfly_valve": "Дисковый затвор",
    "gate_valve": "Задвижка", "flange": "Фланец",
    "check_valve": "Обратный клапан", "filter": "Фильтр",
    "flanged": "Фланцевое", "welded": "Приварное",
    "threaded": "Резьбовое", "wafer": "Межфланцевое",
    "compression": "Компрессионное",
    "male_female": "НР/ВР", "female_female": "ВР/ВР", "male_male": "НР/НР",
    "steel": "Сталь", "brass": "Латунь", "full": "Полнопроходной",
    "reduced": "Стандартнопроходной", "manual": "Ручное",
    "gearbox": "Редуктор", "electric": "Электропривод",
    "electric_ready": "Под электропривод", "pneumatic": "Пневмопривод",
    "standard": "Стандартное", "underground": "Подземное",
    "regulating": "Регулирующее",
}


class DemoRequest(BaseModel):
    products: list[str] = Field(min_length=1, max_length=100)

    @field_validator("products")
    @classmethod
    def check_products(cls, values: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > 2000 for v in values):
            raise ValueError("Каждая позиция должна содержать 1–2000 символов")
        return values


def parameter_rows(interpretation: dict[str, Any]) -> list[dict[str, Any]]:
    extracted = interpretation.get("constraints") or {}
    hard = interpretation.get("hard_constraints") or {}
    extracted = extracted if isinstance(extracted, dict) else {}
    hard = hard if isinstance(hard, dict) else {}
    result = []
    for field, label in FIELDS.items():
        value = extracted.get(field)
        if value in (None, "", "other", "unknown"):
            continue
        if field == "dn":
            shown = "DN " + str(value)
        elif field == "pn_min_mpa":
            try:
                v = float(value)
                shown = f"{v:g} МПа (PN{v*10:g})"
            except (TypeError, ValueError):
                shown = str(value)
        else:
            shown = VALUES.get(str(value), str(value))
        strict = hard.get(field) not in (None, "", "other", "unknown")
        result.append({
            "key": field, "label": label, "value": shown,
            "check": "Строгое условие" if strict else "Интерпретация",
        })
    return result


def as_variant(candidate: Any, selected: Any = None) -> dict[str, Any]:
    return {
        "ld_id": candidate.ld_id,
        "name": candidate.name,
        "article": candidate.article,
        "dn": candidate.dn,
        "pn": candidate.pn,
        "joining_type": candidate.joining_type,
        "score": candidate.score,
        "llm_confidence": getattr(selected, "llm_confidence", None),
        "reason": getattr(selected, "reason", None),
        "selection": "RECOMMENDED" if selected is not None else "FOR_REVIEW",
    }


def build_demo_item(match: Any, duration_ms: float) -> dict[str, Any]:
    interpretation = match.query_interpretation or {}
    if not isinstance(interpretation, dict):
        interpretation = {}
    pool = list(match.candidates or [])
    indexed = {c.ld_id: c for c in pool}
    if match.ld_product is not None:
        indexed[match.ld_product.ld_id] = match.ld_product
    recommended = []
    chosen = set()
    if match.status == "MATCHED":
        for s in match.selected or []:
            c = indexed.get(s.ld_id)
            if c is not None and c.ld_id not in chosen:
                recommended.append(as_variant(c, s))
                chosen.add(c.ld_id)
        if not recommended and match.ld_product is not None:
            recommended = [as_variant(match.ld_product)]
            recommended[0]["selection"] = "RECOMMENDED"
            chosen.add(match.ld_product.ld_id)
    alternatives = [as_variant(c) for c in pool if c.ld_id not in chosen][:5]
    status = "ERROR" if match.status == "RERANK_FAILED" else match.status
    reason = str(match.reason or "")
    if status == "ERROR":
        message = "Ошибка этапа обработки. Повторите запрос."
    elif reason.startswith("HARD_CONSTRAINT_FILTER"):
        message = "Среди найденных кандидатов нет подтверждённого соответствия строгим условиям."
    elif reason.startswith("QUERY_REJECTED"):
        message = "Недостаточно данных либо позиция вне области текущего поиска."
    elif status == "NOT_FOUND":
        message = "Подходящий товар не подтверждён. Это не доказывает отсутствие аналога в каталоге."
    else:
        message = "Рекомендации получены после технической фильтрации и ранжирования."
    return {
        "input": match.query,
        "status": status,
        "message": message,
        "normalized_query": interpretation.get("normalized_query") or match.query,
        "parameters": parameter_rows(interpretation),
        "recommended": recommended,
        "other_candidates": alternatives,
        "metrics": {
            "latency_ms": round(duration_ms, 1),
            "retrieved_count": len(pool),
            "recommended_count": len(recommended),
            "retrieval_score": match.score,
        },
    }


@router.get("/demo", response_class=HTMLResponse, include_in_schema=False)
def business_page() -> HTMLResponse:
    return HTMLResponse(
        (Path(__file__).parent / "business_demo.html").read_text(encoding="utf-8")
    )


@router.post("/v1/demo/match")
def business_match(payload: DemoRequest, request: Request) -> dict[str, Any]:
    runtime = request.app.state.runtime
    if len(payload.products) > runtime.settings.api_max_batch_size:
        raise HTTPException(status_code=413, detail="Размер пакета превышает лимит")
    started = perf_counter()
    results = []
    for product in payload.products:
        item_started = perf_counter()
        try:
            match = runtime.matcher.match_one_hybrid_with_rerank(product.strip())
            results.append(build_demo_item(match, (perf_counter() - item_started)*1000))
        except Exception:
            # Never disclose provider exceptions, tokens, or stack traces in demo DTO.
            results.append({
                "input": product, "status": "ERROR",
                "message": "Сервис подбора временно недоступен.",
                "normalized_query": product, "parameters": [],
                "recommended": [], "other_candidates": [],
                "metrics": {"latency_ms": round((perf_counter()-item_started)*1000, 1),
                            "retrieved_count": 0, "recommended_count": 0,
                            "retrieval_score": None},
            })
    return {
        "request_id": get_request_id(),
        "results": results,
        "latency_ms": round((perf_counter()-started)*1000, 1),
        "accuracy_note": (
            "LLM confidence и retrieval score — не вероятность правильного ответа; "
            "доля MATCHED — не метрика точности."
        ),
    }
