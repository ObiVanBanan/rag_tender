from __future__ import annotations

import re
from enum import StrEnum
from typing import Any


class WorkingMedium(StrEnum):
    GAS = "GAS"
    LIQUID = "LIQUID"
    UNKNOWN = "UNKNOWN"


class CatalogMedium(StrEnum):
    GAS = "GAS"
    LIQUID = "LIQUID"
    BOTH = "BOTH"
    UNKNOWN = "UNKNOWN"


class MediumDisposition(StrEnum):
    MEDIUM_MATCH_REVIEW_REQUIRED = "MEDIUM_MATCH_REVIEW_REQUIRED"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"
    BLOCKED_CONFLICT = "BLOCKED_CONFLICT"


_GAS_TERMS = (
    "газ", "метан", "пропан", "бутан", "биогаз", "водород", "gas",
    "methane", "propane", "butane", "biogas", "hydrogen",
)
_LIQUID_TERMS = (
    "вода", "воды", "воду", "водян", "водоснабж", "жидк", "масло", "нефть", "гликол", "теплоносител",
    "water", "liquid", "fluid", "oil", "glycol",
)


def _contains_term(text: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        suffix = r"(?![\w])" if term == "gas" else r"\w*"
        for match in re.finditer(rf"(?<![\w]){re.escape(term)}{suffix}", text):
            prefix = text[max(0, match.start() - 24) : match.start()]
            if re.search(r"(?:не|без|кроме)(?:\s+для)?\s*$", prefix):
                continue
            remainder = text[match.end() :]
            clause = re.split(r"[,;/]", remainder, maxsplit=1)[0]
            if re.match(
                r"\s*(?:не\s+(?:применяется|допускается|подходит|используется|предназначен)|исключен|запрещен)",
                clause,
            ):
                continue
            return True
    return False


def classify_medium_text(values: list[str]) -> CatalogMedium:
    clauses = [
        part.strip().lower().replace("ё", "е")
        for value in values
        for part in re.split(r"[,;/]+", value)
        if part.strip()
    ]
    categories: set[CatalogMedium] = set()
    for clause in clauses:
        has_gas = _contains_term(clause, _GAS_TERMS)
        has_liquid = _contains_term(clause, _LIQUID_TERMS)
        if has_gas and has_liquid:
            # A single catalog value may state "вода и газ" without separators.
            # Both explicitly allowed phases must be retained, rather than
            # demoting the product to UNKNOWN and losing useful evidence.
            categories.update({CatalogMedium.GAS, CatalogMedium.LIQUID})
            continue
        if has_gas:
            categories.add(CatalogMedium.GAS)
        if has_liquid:
            categories.add(CatalogMedium.LIQUID)
    if len(categories) > 1:
        return CatalogMedium.BOTH
    if categories:
        return next(iter(categories))
    return CatalogMedium.UNKNOWN


def medium_property_values(properties: Any) -> list[str]:
    values: list[str] = []
    for item in properties or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().lower().replace("ё", "е")
        if name != "рабочая среда":
            continue
        raw = item.get("values")
        raw_values = raw if isinstance(raw, list) else [raw]
        for raw_value in raw_values:
            if raw_value is None:
                continue
            values.extend(
                part.strip()
                for part in re.split(r"[,;/]+", str(raw_value))
                if part.strip()
            )
    return values


def catalog_medium(properties: Any) -> CatalogMedium:
    """Classify only the structured `Рабочая среда` catalog property.

    Product names and model-generated explanations are intentionally excluded:
    neither is reliable evidence of the intended service medium.
    """
    return classify_medium_text(medium_property_values(properties))


def medium_matches(requested_value: str, properties: Any) -> bool:
    """Compare service phases; gas species are intentionally equivalent here."""
    requested = classify_medium_text([requested_value])
    actual = catalog_medium(properties)
    if actual is CatalogMedium.BOTH:
        return requested in {CatalogMedium.GAS, CatalogMedium.LIQUID}
    if requested is CatalogMedium.UNKNOWN and actual is CatalogMedium.UNKNOWN:
        expected = requested_value.strip().lower().replace("ё", "е")
        return expected in {
            value.strip().lower().replace("ё", "е")
            for value in medium_property_values(properties)
        }
    if requested is CatalogMedium.UNKNOWN or actual is CatalogMedium.UNKNOWN:
        return False
    return requested is actual


def medium_disposition(
    requested: WorkingMedium,
    actual: CatalogMedium,
) -> MediumDisposition:
    if requested is WorkingMedium.UNKNOWN:
        return MediumDisposition.NEEDS_EVIDENCE
    if actual is CatalogMedium.UNKNOWN:
        return MediumDisposition.NEEDS_EVIDENCE
    if actual is CatalogMedium.BOTH:
        return MediumDisposition.MEDIUM_MATCH_REVIEW_REQUIRED
    if requested.value == actual.value:
        return MediumDisposition.MEDIUM_MATCH_REVIEW_REQUIRED
    return MediumDisposition.BLOCKED_CONFLICT
