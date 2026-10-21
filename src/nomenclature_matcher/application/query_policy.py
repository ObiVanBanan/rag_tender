"""Application policies for preparing query constraints and enrichment."""

from ..domain.constraints import (
    canonical_bore_type,
    canonical_control,
    canonical_material,
    canonical_product_type,
)
from ..domain.query_signals import (
    explicit_dn_from_query,
    explicit_joining_type_from_query,
    explicit_pn_mpa_from_query,
    explicit_technical_signal_count,
    explicit_thread_type_from_query,
    explicit_working_medium_from_query,
    has_product_identity,
)


def enrichment_gate(query: str, interpretation, *, lookup_enabled: bool) -> tuple[bool, str]:
    """Decide whether web lookup can add useful identity evidence."""
    if not lookup_enabled:
        return False, "enrichment_disabled"
    constraints = interpretation.constraints
    if constraints.catalog_scope == "out_of_scope":
        return False, "pre_enrichment_out_of_scope"
    if not has_product_identity(query):
        return False, "pre_enrichment_no_product_identity"
    if explicit_technical_signal_count(query) >= 4:
        return False, "pre_enrichment_enough_explicit_detail"
    if (
        not interpretation.searchable
        and not constraints.ambiguous
        and constraints.catalog_scope != "uncertain"
    ):
        return False, "pre_enrichment_not_searchable"
    if constraints.ambiguous:
        return True, "pre_enrichment_ambiguous_identity_rescue"
    return True, "pre_enrichment_eligible"


def hard_constraints(query: str, pre_interpretation, enriched_interpretation=None) -> dict:
    """Build hard filters from explicit query facts; deductions stay soft."""
    pre = pre_interpretation.constraints
    enriched = enriched_interpretation.constraints if enriched_interpretation is not None else None
    explicit_product_type = canonical_product_type(query)
    if explicit_product_type == "other":
        product_type = (
            enriched.product_type
            if enriched is not None and enriched.product_type != "other"
            else pre.product_type
        )
    else:
        product_type = explicit_product_type

    material = canonical_material(query)
    if material == "other":
        material = None
    bore = canonical_bore_type(query)
    control = canonical_control(query)
    designation = None
    if pre.valve_designation:
        query_compact = "".join(ch for ch in query.lower() if ch.isalnum())
        designation_compact = "".join(ch for ch in str(pre.valve_designation).lower() if ch.isalnum())
        if designation_compact and designation_compact in query_compact:
            designation = pre.valve_designation

    text = query.lower().replace("ё", "е")
    valve_type = None
    if "подзем" in text:
        valve_type = "underground"
    elif "регулиру" in text:
        valve_type = "regulating"
    elif "криоген" in text:
        valve_type = "cryogenic"
    elif "газов" in text:
        valve_type = "gas"

    return {
        "product_type": product_type,
        "dn": explicit_dn_from_query(query),
        "pn_min_mpa": explicit_pn_mpa_from_query(query),
        "joining_type": explicit_joining_type_from_query(query),
        "thread_type": explicit_thread_type_from_query(query),
        "working_medium": explicit_working_medium_from_query(query),
        "valve_type": valve_type,
        "valve_designation": designation,
        "body_material": material,
        "body_material_grade": None,
        "bore_type": bore,
        "control": control,
        "catalog_scope": pre.catalog_scope,
        "ambiguous": pre.ambiguous,
        "comment": "hard constraints derived only from explicit QUERY facts",
    }
