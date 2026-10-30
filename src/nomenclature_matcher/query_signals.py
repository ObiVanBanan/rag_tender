"""Compatibility exports for domain query-signal policies."""

from .domain.query_signals import (
    exact_product_identity_anchors,
    explicit_dn_from_query,
    explicit_joining_type_from_query,
    explicit_pn_mpa_from_query,
    explicit_technical_signal_count,
    explicit_thread_type_from_query,
    explicit_working_medium_from_query,
    has_product_identity,
    normalize_query_text,
    product_identity_anchors,
)

__all__ = [
    "exact_product_identity_anchors",
    "explicit_dn_from_query",
    "explicit_joining_type_from_query",
    "explicit_pn_mpa_from_query",
    "explicit_technical_signal_count",
    "explicit_thread_type_from_query",
    "explicit_working_medium_from_query",
    "has_product_identity",
    "normalize_query_text",
    "product_identity_anchors",
]
