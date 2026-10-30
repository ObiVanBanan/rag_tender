from __future__ import annotations

from typing import Any

from ..models import SearchCandidate
from ..query_canonicalization import build_constraint_rendered_query
from ..domain.constraints import QueryConstraints
from .candidate_selection import CandidateSelectionService
from .ports import HybridRetrieverPort, SecondChanceResult


class SecondChanceCandidateRetriever:
    """Additive catalog-vocabulary retrieval that never relaxes hard facts."""

    def __init__(
        self,
        *,
        retriever: HybridRetrieverPort | None,
        settings: Any,
        candidate_selection: CandidateSelectionService,
    ) -> None:
        self.retriever = retriever
        self.settings = settings
        self.candidate_selection = candidate_selection

    def retrieve(
        self,
        constraints: dict[str, Any],
    ) -> SecondChanceResult | None:
        if self.retriever is None:
            return None
        try:
            parsed_constraints = QueryConstraints.model_validate(constraints)
            rendered_query = build_constraint_rendered_query(parsed_constraints)
            if rendered_query is None:
                return None

            retriever_debug = None
            if (
                getattr(self.settings, "match_trace_detailed_enabled", False)
                and hasattr(self.retriever, "search_with_trace")
            ):
                fresh_candidates, retriever_debug = self.retriever.search_with_trace(
                    rendered_query,
                    self.settings.hybrid_rerank_limit,
                )
            else:
                fresh_candidates = self.retriever.search(
                    rendered_query,
                    self.settings.hybrid_rerank_limit,
                )

            if not fresh_candidates:
                return None
            indexed_candidates = self.candidate_selection.eligible_candidates(
                fresh_candidates,
                constraints,
            )
            if not indexed_candidates:
                return None
            return fresh_candidates, indexed_candidates, retriever_debug
        except Exception:
            # This fallback is additive; failures retain the original NOT_FOUND behavior.
            return None
