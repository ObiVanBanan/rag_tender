from __future__ import annotations

from typing import Any


DIAGNOSTIC_CONSTRAINT_FIELDS = (
    "product_type",
    "dn",
    "pn_min_mpa",
    "joining_type",
    "thread_type",
    "working_medium",
    "valve_type",
    "valve_designation",
    "body_material",
    "body_material_grade",
    "bore_type",
    "control",
)


def trim_text(value: Any, limit: int = 600) -> str:
    return " ".join(str(value or "").split())[:limit]


def classify_match_reason(status: str, reason: str | None) -> str:
    if status == "MATCHED":
        return "MATCHED"
    text = str(reason or "").strip()
    upper = text.upper()
    if "HARD_CONSTRAINT_FILTER" in upper:
        return "HARD_CONSTRAINT_FILTER"
    if upper.startswith("QUERY_REJECTED"):
        return "QUERY_REJECTED"
    if upper.startswith("QUERY_INTERPRET_FAILED"):
        return "QUERY_INTERPRET_FAILED"
    if status in {"ERROR", "RERANK_FAILED"} or "RERANK_FAILED" in upper:
        return "RERANK_FAILED"
    if "NO EXACT MATCH" in upper or "NOT_FOUND" in upper:
        return "RERANK_NOT_FOUND"
    if not text:
        return "UNSPECIFIED"
    return "OTHER"


def build_attribute_diagnostic(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    hard: dict[str, Any] | None,
) -> dict[str, Any]:
    before = before or {}
    after = after or {}
    hard = hard or {}
    changed_fields: list[str] = []
    hard_conflicts: dict[str, dict[str, Any]] = {}
    for field in DIAGNOSTIC_CONSTRAINT_FIELDS:
        before_value = before.get(field)
        after_value = after.get(field)
        hard_value = hard.get(field)
        if before_value != after_value:
            changed_fields.append(field)
        if (
            hard_value not in (None, "")
            and after_value not in (None, "")
            and hard_value != after_value
        ):
            hard_conflicts[field] = {"hard": hard_value, "enriched": after_value}
    return {
        "changed_fields": changed_fields,
        "hard_conflict_fields": sorted(hard_conflicts),
        "hard_conflicts": hard_conflicts,
    }
