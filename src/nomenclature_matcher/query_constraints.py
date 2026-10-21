"""Compatibility exports for domain query constraints and product policies.

New application code should import these rules from ``domain.constraints``.
This module remains stable for existing callers and serialized-test fixtures.
"""

from .domain.constraints import (
    MatchDecision,
    QueryConstraints,
    candidate_bore_type,
    candidate_control,
    candidate_dn,
    candidate_has_designation,
    candidate_joining_type,
    candidate_material,
    candidate_material_text,
    candidate_pn_mpa,
    candidate_product_type,
    candidate_thread_type,
    candidate_valve_type,
    canonical_bore_type,
    canonical_control,
    canonical_joining_type,
    canonical_material,
    canonical_product_type,
    canonical_thread_type,
    evaluate_product,
    matching_products,
    product_snapshot,
    technical_compatibility,
)

__all__ = [
    "MatchDecision",
    "QueryConstraints",
    "candidate_bore_type",
    "candidate_control",
    "candidate_dn",
    "candidate_has_designation",
    "candidate_joining_type",
    "candidate_material",
    "candidate_material_text",
    "candidate_pn_mpa",
    "candidate_product_type",
    "candidate_thread_type",
    "candidate_valve_type",
    "canonical_bore_type",
    "canonical_control",
    "canonical_joining_type",
    "canonical_material",
    "canonical_product_type",
    "canonical_thread_type",
    "evaluate_product",
    "matching_products",
    "product_snapshot",
    "technical_compatibility",
]
