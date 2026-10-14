"""Narrow restoration of exp4-style flange joining; 100-case valve path stays unchanged."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from nomenclature_matcher.models import LDProduct
from nomenclature_matcher.query_constraints import (
    QueryConstraints, candidate_joining_type, candidate_material, evaluate_product,
    canonical_material,
)
from nomenclature_matcher.query_interpreter import DeepSeekQueryInterpreter
from nomenclature_matcher.query_signals import (
    explicit_dn_from_query, explicit_joining_type_from_query,
    flange_sleeve_dn_pair,
)

FLANGE_PND = (
    "Фланец стальной ду80мм. под втулку ПНД ду90мм.",
    "Фланец стальной ду50мм. под втулку ПНД ду63мм.",
    "Фланец стальной ду40мм. под втулку ПНД ду50мм.",
    "Фланец стальной ду100мм. под втулку ПНД ду110мм.",
)


@pytest.mark.parametrize("query,flange_dn,sleeve_dn", [
    (FLANGE_PND[0], 80, 90),
    (FLANGE_PND[1], 50, 63),
    (FLANGE_PND[2], 40, 50),
    (FLANGE_PND[3], 100, 110),
])
def test_two_dn_flange_profile_preserves_distinct_roles(query,flange_dn,sleeve_dn):
    assert flange_sleeve_dn_pair(query) == (flange_dn, sleeve_dn)
    assert explicit_dn_from_query(query) == flange_dn
    assert canonical_material(query) == "steel"


def test_two_arbitrary_dn_remain_ambiguous():
    for query in (
        "Кран шаровой Ду80 Ру16 Ду90",
        "Фланец стальной Ду80 Ду90",
        "Фланец стальной Ду80 под втулку ПНД Ду90, Ду100",
        "Кран шаровой Ду80 под втулку ПНД Ду90",
    ):
        assert flange_sleeve_dn_pair(query) is None
        assert explicit_dn_from_query(query) is None


def test_flange_joining_restored_only_for_flange_product():
    source="Фланец стальной плоский приварной, марка стали 20, номинальное давление 1,6 МПа, номинальный диаметр 100 мм"
    assert explicit_joining_type_from_query(source) == "flanged"
    assert explicit_joining_type_from_query("Кран шаровой приварной DN100 PN16") == "welded"
    flange=LDProduct(
        id=42, name="Фланец LD стальной плоский приварной DN100 PN16",
        article="F-42",dn="100",pn="1,6",joining_type="Приварное",
    )
    welded_valve=LDProduct(
        id=43, name="Кран шаровой LD стальной приварной Ду100 Ру16",
        article="B-43",dn="100",pn="1,6",joining_type="Приварное",
    )
    assert candidate_joining_type(flange) == "flanged"
    assert candidate_joining_type(welded_valve) == "welded"
    assert evaluate_product(flange,QueryConstraints(
        product_type="flange",dn=100,pn_min_mpa=1.6,
        joining_type="flanged",body_material="steel",
        catalog_scope="in_scope",ambiguous=False,
    )).matches


def _sanitize(query, constraints):
    interpreter=object.__new__(DeepSeekQueryInterpreter)
    interpreter.settings=SimpleNamespace(competitor_decoder_baseline_enabled=False)
    return interpreter._sanitize_payload(query, {
        "searchable": False, "normalized_query":query,"reason":"initial",
        "constraints":{
            "product_type":constraints["product_type"],
            "dn":constraints.get("dn"),
            "pn_min_mpa":None,
            "joining_type":None,
            "thread_type":None,
            "working_medium":None,
            "valve_type":None,
            "valve_designation":None,
            "body_material":constraints.get("body_material"),
            "body_material_grade":None,
            "bore_type":None,
            "control":None,
            "catalog_scope":"in_scope",
            "ambiguous":False,
            "comment":"",
        },
    })


def test_interpreter_corrects_pnd_sleeve_not_steel_flange():
    result=_sanitize(FLANGE_PND[0],{
        "product_type":"flange","dn":90,"body_material":"polyethylene",
    })
    assert result["constraints"]["dn"] == 80
    assert result["constraints"]["body_material"] == "steel"
    assert result["searchable"] is True


@pytest.mark.parametrize("query,product_type,dn",[
    ("фильтр Ду50", "filter", 50),
    ("кран шаровый Ду150", "ball_valve", 150),
    ("кран шаровый Ду25", "ball_valve", 25),
])
def test_insufficient_attribute_gate_unchanged(query,product_type,dn):
    result=_sanitize(query,{"product_type":product_type,"dn":dn})
    assert result["searchable"] is False


def test_frozen100_query_cohort_does_not_trigger_flange_changes():
    # This is a scope assertion only, NOT a substitute for live metric replay.
    trace=(Path(__file__).resolve().parents[1]/
        "docs/experiments/traces/E08-wide-prefilter-seed53.json")
    data=json.loads(trace.read_text(encoding="utf-8"))
    assert data["sample"] == 100 and data["seed"] == 53
    assert len(data["cases"]) == 100
    for case in data["cases"]:
        query=case["query"].lower().replace("ё","е")
        assert not __import__("re").search(r"(?<![а-яa-z])фланец(?![а-яa-z])",query)
        assert flange_sleeve_dn_pair(query) is None


def test_missing_material_is_not_created_for_unrelated_flange():
    assert canonical_material("Фланец полиэтиленовый Ду90") == "polyethylene"
    assert canonical_material("Кран шаровой стальной с ПНД футеровкой") == "polyethylene"
