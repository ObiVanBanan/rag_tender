"""Regression coverage for production hardening: phases, joining and PN notation."""

import pytest

from nomenclature_matcher.api import AnalystQuery
from nomenclature_matcher.domain.constraints import (
    candidate_pn_mpa,
    canonical_joining_type,
)
from nomenclature_matcher.domain.medium import (
    CatalogMedium,
    WorkingMedium,
    classify_medium_text,
    medium_disposition,
)
from nomenclature_matcher.domain.product import LDProduct
from nomenclature_matcher.domain.query_signals import (
    explicit_joining_type_from_query,
    explicit_working_medium_from_query,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("PN10", 1.0),
        ("Ру10", 1.0),
        ("PN6", 0.6),
        ("PN16", 1.6),
        ("Ру1,0МПа", 1.0),
        ("1,6", 1.6),
    ],
)
def test_pn_pressure_class_and_explicit_mpa_are_not_confused(raw, expected):
    product = LDProduct(id=1, name="Кран шаровой", pn=raw)
    assert candidate_pn_mpa(product) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Фланцевое / приварное", "mixed_flange_weld"),
        ("Фланцевое", "flanged"),
        ("Цельносварной фланцевый кран", "flanged"),
        ("Штуцерное", "fitting"),
        ("Приварное", "welded"),
        ("Муфтовое", "threaded"),
    ],
)
def test_catalog_pipe_end_kind_is_not_silently_collapsed(source, expected):
    assert canonical_joining_type(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Кран фланцевый/приварной DN50", "mixed_flange_weld"),
        ("Кран фланец/приварка DN50", "mixed_flange_weld"),
        ("Кран цельносварной фланцевый DN50", "flanged"),
        ("Кран штуцерного соединения DN40", "fitting"),
        ("Кран с муфтовым соединением", "threaded"),
    ],
)
def test_query_joint_detection_preserves_ends(source, expected):
    assert explicit_joining_type_from_query(source) == expected


def test_gas_and_water_in_one_catalog_property_are_both():
    assert classify_medium_text(["Вода и газ"]) is CatalogMedium.BOTH
    assert classify_medium_text(["газ, вода"]) is CatalogMedium.BOTH
    assert medium_disposition(WorkingMedium.GAS, CatalogMedium.BOTH).value == (
        "MEDIUM_MATCH_REVIEW_REQUIRED"
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Кран для газа DN25", "газ"),
        ("Кран газовый DN25", "газ"),
        ("Арматура для воды DN25", "вода"),
        ("Кран для водяной системы", "вода"),
    ],
)
def test_source_medium_detects_common_russian_inflections(source, expected):
    assert explicit_working_medium_from_query(source) == expected


def test_shortlist_cannot_override_explicit_gas_use_with_liquid():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AnalystQuery(query="Кран газовый DN25", working_medium=WorkingMedium.LIQUID)


def test_shortlist_cannot_override_explicit_water_use_with_gas():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AnalystQuery(query="Кран для воды DN25", working_medium=WorkingMedium.GAS)
