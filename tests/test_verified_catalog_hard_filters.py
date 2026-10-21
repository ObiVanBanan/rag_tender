"""Manufacturer evidence is authoritative, but uncertainty cannot be guessed."""

from types import SimpleNamespace
import pytest

from nomenclature_matcher.competitor_resolver import CompetitorResolver
from nomenclature_matcher.application.query_policy import (
    apply_verified_catalog_constraints,
    hard_constraints,
)
from nomenclature_matcher.domain.competitor import CompetitorResolution, ResolvedFact
from nomenclature_matcher.domain.constraints import canonical_control, candidate_control, QueryConstraints, evaluate_product
from nomenclature_matcher.domain.product import LDProduct


def resolver(tmp_path):
    return CompetitorResolver(SimpleNamespace(
        competitor_kb_path=str(tmp_path / "kb.sqlite3"),
        competitor_catalog_registry_path="data/competitor_catalogs/sources.json",
    ))


def query_explicit(raw, **overrides):
    values = {"product_type": "ball_valve", "dn": None, "pn_min_mpa": None,
        "joining_type": None, "thread_type": None, "working_medium": None,
        "valve_type": None, "valve_designation": None, "body_material": None,
        "body_material_grade": None, "bore_type": None, "control": None,
        "catalog_scope": "in_scope", "ambiguous": False, "comment": ""}
    values.update(overrides)
    interpretation = SimpleNamespace(constraints=SimpleNamespace(**values))
    return hard_constraints(raw, interpretation)


def test_catalog_drive_becomes_a_hard_rejection_of_manual_ld(tmp_path):
    source = resolver(tmp_path).resolve("Кран шаровой MARSHAL 11с67п ЦФ.00.9.016.050")
    hard, conflicts = apply_verified_catalog_constraints(query_explicit("Кран шаровой MARSHAL 11с67п ЦФ.00.9.016.050"), source)
    assert not conflicts
    assert hard["control"] == "electric"
    assert hard["joining_type"] == "flanged"
    manual = LDProduct(id=1, name="Кран шаровый фланцевый Ду50 Ру1,6МПа ручной", dn="50", pn="1.6", joining_type="Фланцевое")
    assert evaluate_product(manual, QueryConstraints.model_validate(hard)).matches is False


def test_conflicting_human_text_and_exact_catalog_never_silently_overrides(tmp_path):
    query = "Кран шаровой MARSHAL 11с67п ЦФ.00.9.016.050 ручной"
    source = resolver(tmp_path).resolve(query)
    hard, conflicts = apply_verified_catalog_constraints(query_explicit(query), source)
    assert conflicts == ["control"]
    assert hard["control"] == "manual"


def test_missing_candidate_actuation_is_not_assumed_manual():
    product = LDProduct(id=2, name="Кран шаровый DN50 PN16", dn="50", pn="1.6")
    assert candidate_control(product) is None


@pytest.mark.parametrize(("description", "control"), [
    ("под редуктор", "gearbox_ready"),
    ("под привод", "actuator_ready"),
    ("с пневмогидравлическим приводом", "pneumohydraulic"),
    ("с гидроприводом", "hydraulic"),
    ("с электроприводом", "electric"),
])
def test_drive_states_are_not_collapsed(description, control):
    assert canonical_control(description) == control


def test_supported_web_facts_do_not_become_verified_hard_filters():
    source = CompetitorResolution(
        status="WEB_LEARNED", identity_level="EXACT_PRODUCT",
        identity_key="acme:xyz", identity_anchor="xyz",
        facts={"control": ResolvedFact("electric", "SUPPORTED", [])},
    )
    hard, conflicts = apply_verified_catalog_constraints({"control": None}, source)
    assert hard["control"] is None
    assert not conflicts
