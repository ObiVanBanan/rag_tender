from __future__ import annotations

from typing import Any, Callable

from ..models import MatchResult, SearchCandidate, SelectedMatch
from ..domain.constraints import QueryConstraints, evaluate_product, product_snapshot
from .candidate_selection import CandidateSelectionService
from .ports import RerankerPort, SecondChanceResult


SecondChanceProvider = Callable[
    [dict[str, Any]], SecondChanceResult | None
]


class CandidateRerankingService:
    """Apply the hard-constraint gate, optional second chance, and model ranking."""

    def __init__(
        self,
        *,
        settings: Any,
        reranker: RerankerPort | None,
        candidate_selection: CandidateSelectionService,
        second_chance: SecondChanceProvider,
    ) -> None:
        self.settings = settings
        self.reranker = reranker
        self.candidate_selection = candidate_selection
        self.second_chance = second_chance

    @staticmethod
    def _build_selected_match(
        candidate: SearchCandidate,
        item,
        *,
        candidate_id: int | None = None,
    ) -> SelectedMatch:
        return SelectedMatch(
            candidate_id=candidate_id if candidate_id is not None else item.candidate_id,
            article=candidate.article,
            name=candidate.name,
            llm_confidence=item.confidence,
            reason=item.reason,
            ld_id=candidate.ld_id,
            dense_score=candidate.dense_score,
            bm25_score=candidate.bm25_score,
            rrf_score=candidate.rrf_score,
            dn=candidate.dn,
            pn=candidate.pn,
            joining_type=candidate.joining_type,
            url=candidate.url,
        )

    def rerank_candidates(
        self,
        query: str,
        candidates: list[SearchCandidate],
        *,
        constraints: dict | None = None,
        query_interpretation: dict | None = None,
        rerank_query: str | None = None,
    ) -> MatchResult:
        if not candidates:
            return MatchResult(
                query=query,
                status="NOT_FOUND",
                candidates=[],
                query_interpretation=query_interpretation,
            )
        if self.reranker is None:
            raise ValueError("Reranker is not configured")

        candidate_pool = candidates
        indexed_candidates = list(enumerate(candidate_pool, 1))
        retrieval_trace = None
        if isinstance(query_interpretation, dict):
            maybe_trace = query_interpretation.get("retrieval_trace")
            if isinstance(maybe_trace, dict):
                retrieval_trace = maybe_trace
                retrieval_trace["initial_candidate_count"] = len(candidate_pool)
                retrieval_trace["initial_candidate_ids"] = [
                    candidate.ld_id for candidate in candidate_pool
                ]
                retrieval_trace["initial_candidates"] = [
                    {
                        "ld_id": candidate.ld_id,
                        "name": candidate.name,
                        "article": candidate.article,
                        "dense_rank": candidate.dense_rank,
                        "bm25_rank": candidate.bm25_rank,
                        "rrf_score": candidate.rrf_score,
                        "retrieval_sources": candidate.retrieval_sources,
                    }
                    for candidate in candidate_pool
                ]
                if getattr(self.settings, "match_trace_detailed_enabled", False):
                    parsed_trace_constraints = (
                        QueryConstraints.model_validate(constraints)
                        if constraints is not None
                        else None
                    )
                    retrieval_trace["initial_candidate_snapshots"] = [
                        {
                            "input_rank": index,
                            "dense_rank": candidate.dense_rank,
                            "bm25_rank": candidate.bm25_rank,
                            "rrf_score": candidate.rrf_score,
                            "retrieval_sources": list(candidate.retrieval_sources),
                            "product": product_snapshot(
                                self.candidate_selection.candidate_as_product(candidate),
                                parsed_trace_constraints,
                            ),
                            "matches_hard_constraints": (
                                evaluate_product(
                                    self.candidate_selection.candidate_as_product(candidate),
                                    parsed_trace_constraints,
                                ).matches
                                if parsed_trace_constraints is not None
                                else None
                            ),
                        }
                        for index, candidate in enumerate(candidate_pool, 1)
                    ]

        if constraints is not None:
            indexed_candidates = self.candidate_selection.eligible_candidates(
                candidate_pool, constraints
            )
            if retrieval_trace is not None:
                retrieval_trace["eligible_candidate_count_before_second_chance"] = len(
                    indexed_candidates
                )
                retrieval_trace["eligible_candidate_ids_before_second_chance"] = [
                    candidate.ld_id for _, candidate in indexed_candidates
                ]
            if not indexed_candidates:
                second_chance = self.second_chance(constraints)
                if second_chance is None:
                    if retrieval_trace is not None:
                        retrieval_trace["second_chance_used"] = False
                        retrieval_trace["rerank_candidate_count"] = 0
                        retrieval_trace["rerank_candidate_ids"] = []
                        retrieval_trace["failure_stage"] = "hard_constraint_filter"
                    return MatchResult(
                        query=query,
                        status="NOT_FOUND",
                        candidates=candidate_pool,
                        reason="HARD_CONSTRAINT_FILTER: no retrieved candidate satisfies all QUERY_CONSTRAINTS",
                        query_interpretation=query_interpretation,
                    )
                candidate_pool, indexed_candidates, second_chance_debug = second_chance
                if retrieval_trace is not None:
                    retrieval_trace["second_chance_used"] = True
                    retrieval_trace["second_chance_candidate_ids"] = [
                        candidate.ld_id for candidate in candidate_pool
                    ]
                    retrieval_trace["eligible_candidate_ids_after_second_chance"] = [
                        candidate.ld_id for _, candidate in indexed_candidates
                    ]
                    if second_chance_debug is not None:
                        retrieval_trace["second_chance_retriever"] = second_chance_debug
            elif retrieval_trace is not None:
                retrieval_trace["second_chance_used"] = False

        rerank_input = [candidate for _, candidate in indexed_candidates]
        if retrieval_trace is not None:
            retrieval_trace["rerank_candidate_count"] = len(rerank_input)
            retrieval_trace["rerank_candidate_ids"] = [
                candidate.ld_id for candidate in rerank_input
            ]
        effective_rerank_query = rerank_query or query
        if retrieval_trace is not None:
            retrieval_trace["rerank_query"] = effective_rerank_query
        try:
            if constraints is None:
                rerank_result = self.reranker.rerank(effective_rerank_query, rerank_input)
            else:
                rerank_result = self.reranker.rerank(
                    effective_rerank_query,
                    rerank_input,
                    constraints=constraints,
                )
        except Exception as exc:
            if retrieval_trace is not None:
                retrieval_trace["failure_stage"] = "reranker_exception"
                retrieval_trace["reranker_error"] = f"{type(exc).__name__}: {exc}"
            return MatchResult(
                query=query,
                status="RERANK_FAILED",
                score=candidates[0].score,
                ld_product=None,
                candidates=candidate_pool,
                reason=str(exc),
                query_interpretation=query_interpretation,
            )

        selected = []
        selected_candidates: list[SearchCandidate] = []
        for item in rerank_result.selected:
            original_candidate_id, candidate = indexed_candidates[item.candidate_id - 1]
            selected.append(
                self._build_selected_match(
                    candidate,
                    item,
                    candidate_id=original_candidate_id,
                )
            )
            selected_candidates.append(candidate)

        best = selected_candidates[0] if selected_candidates else None
        if retrieval_trace is not None:
            retrieval_trace["reranker_status"] = rerank_result.status
            retrieval_trace["reranker_reason"] = rerank_result.reason
            retrieval_trace["selected_ld_ids"] = [
                candidate.ld_id for candidate in selected_candidates
            ]
            retrieval_trace["reranker_selected"] = [
                {
                    "candidate_id": selected_item.candidate_id,
                    "ld_id": selected_item.ld_id,
                    "confidence": selected_item.llm_confidence,
                    "reason": selected_item.reason,
                }
                for selected_item in selected
            ]
            if rerank_result.status == "MATCHED" and selected_candidates:
                retrieval_trace["failure_stage"] = None
            elif rerank_input:
                retrieval_trace["failure_stage"] = "reranker"
        return MatchResult(
            query=query,
            status=rerank_result.status,
            score=best.score if best else None,
            ld_product=best if rerank_result.status == "MATCHED" else None,
            candidates=candidate_pool,
            selected=selected,
            reason=rerank_result.reason,
            query_interpretation=query_interpretation,
        )
