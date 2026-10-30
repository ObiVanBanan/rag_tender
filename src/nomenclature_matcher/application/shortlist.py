from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from ..domain.medium import (
    WorkingMedium,
    catalog_medium,
    medium_disposition,
)
from ..models import MatchResult, SearchCandidate
from ..domain.query_signals import explicit_working_medium_from_query
from .ports import MatcherPort

logger = logging.getLogger(__name__)


def _candidate_payload(
    candidate: SearchCandidate,
    *,
    rank: int,
    selected_rank: int | None,
    selected_confidence: float | None,
    selected_reason: str | None,
    requested_medium: WorkingMedium,
) -> dict[str, Any]:
    actual_medium = catalog_medium(candidate.properties)
    disposition = medium_disposition(requested_medium, actual_medium)
    return {
        "rank": rank,
        "ld_id": candidate.ld_id,
        "article": candidate.article,
        "name": candidate.name,
        "url": candidate.url,
        "retrieval_score": candidate.score,
        "dense_score": candidate.dense_score,
        "dense_rank": candidate.dense_rank,
        "bm25_score": candidate.bm25_score,
        "bm25_rank": candidate.bm25_rank,
        "rrf_score": candidate.rrf_score,
        "retrieval_sources": candidate.retrieval_sources,
        "attributes": {
            "dn": candidate.dn,
            "pn": candidate.pn,
            "joining_type": candidate.joining_type,
        },
        "properties": candidate.properties or [],
        "reranker": {
            "selected": selected_rank is not None,
            "selected_rank": selected_rank,
            "confidence": selected_confidence,
            "reason": selected_reason,
        },
        "working_medium": {
            "requested": requested_medium.value,
            "catalog_classification": actual_medium.value,
            "disposition": disposition.value,
        },
        "gas_certification": "UNVERIFIED",
        "human_review_required": True,
        "automatic_approval": False,
    }


def build_analyst_shortlist(
    result: MatchResult,
    requested_medium: WorkingMedium,
    *,
    max_candidates: int = 20,
) -> dict[str, Any]:
    """Build an auditable response from one existing retrieval/rerank result."""
    if not 1 <= max_candidates <= 20:
        raise ValueError("max_candidates must be between 1 and 20")

    selected_by_id = {item.ld_id: (rank, item) for rank, item in enumerate(result.selected, 1)}
    # Keep the matcher-provided order: it is the technical-prefilter pool rank.
    ordered = result.candidates

    suggestions: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for rank, candidate in enumerate(ordered[:max_candidates], 1):
        selected = selected_by_id.get(candidate.ld_id)
        payload = _candidate_payload(
            candidate,
            rank=rank,
            selected_rank=selected[0] if selected else None,
            selected_confidence=selected[1].llm_confidence if selected else None,
            selected_reason=selected[1].reason if selected else None,
            requested_medium=requested_medium,
        )
        disposition = payload["working_medium"]["disposition"]
        if disposition == "BLOCKED_CONFLICT":
            blocked.append(payload)
        else:
            suggestions.append(payload)

    error = result.status == "RERANK_FAILED"
    status = "ERROR" if error else ("REVIEW_REQUIRED" if suggestions else "NO_CANDIDATES")
    return {
        "input": result.query,
        "status": status,
        "error_code": "RERANK_FAILED" if error else None,
        "requested_medium": requested_medium.value,
        "decision": "REVIEW_REQUIRED",
        "human_review_required": True,
        "automatic_approval": False,
        "candidates": suggestions,
        "blocked_candidates": blocked,
        "candidate_count": len(suggestions),
        "blocked_candidate_count": len(blocked),
        "candidate_pool_truncated": len(result.candidates) > max_candidates,
        "pool_size": len(result.candidates),
    }


def shortlist_product(
    matcher: MatcherPort,
    query: str,
    requested_medium: WorkingMedium,
    *,
    max_candidates: int = 20,
) -> dict[str, Any]:
    """Application use case: run matching once and return review-only evidence."""
    try:
        matcher_query = query
        if explicit_working_medium_from_query(query) is None:
            qualifier = {
                WorkingMedium.GAS: "газ",
                WorkingMedium.LIQUID: "вода",
            }.get(requested_medium)
            if qualifier:
                matcher_query = f"{query} Рабочая среда {qualifier}"
        result = matcher.match_one_hybrid_with_rerank(matcher_query)
        result = replace(result, query=query)
        return build_analyst_shortlist(
            result,
            requested_medium,
            max_candidates=max_candidates,
        )
    except Exception as exc:
        logger.exception("Analyst shortlist failed for one item")
        return {
            "input": query,
            "status": "ERROR",
            "error_code": type(exc).__name__,
            "requested_medium": requested_medium.value,
            "decision": "REVIEW_REQUIRED",
            "human_review_required": True,
            "automatic_approval": False,
            "candidates": [],
            "blocked_candidates": [],
            "candidate_count": 0,
            "blocked_candidate_count": 0,
            "candidate_pool_truncated": False,
            "pool_size": 0,
        }
