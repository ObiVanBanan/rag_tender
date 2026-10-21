from __future__ import annotations

from typing import Any

from ..models import MatchResult
from .diagnostics import trim_text
from .candidate_reranking import CandidateRerankingService, SecondChanceProvider
from .candidate_selection import CandidateSelectionService
from .ports import HybridRetrieverPort, RerankerPort, TelemetryPort
from .telemetry import NullTelemetry


class HybridCandidateSearchService:
    """Retrieve a bounded hybrid pool, prefilter it, then rerank once."""

    def __init__(
        self,
        *,
        settings: Any,
        retriever: HybridRetrieverPort,
        reranker: RerankerPort | None,
        telemetry: TelemetryPort | None = None,
    ) -> None:
        self.settings = settings
        self.retriever = retriever
        self.reranker = reranker
        self.telemetry = telemetry or NullTelemetry()
        self.selection = CandidateSelectionService()

    def execute(
        self,
        *,
        query: str,
        retrieval_query: str,
        canonical_query: str | None,
        retrieval_strategy: str,
        soft_constraints: dict[str, Any],
        hard_constraints: dict[str, Any],
        query_interpretation: dict[str, Any],
        second_chance: SecondChanceProvider,
        prefilter_pool_limit: int | None = None,
    ) -> MatchResult:
        detailed_trace = bool(
            getattr(self.settings, "match_trace_detailed_enabled", False)
        )
        pool_limit = max(
            self.settings.hybrid_rerank_limit,
            int(prefilter_pool_limit)
            if prefilter_pool_limit is not None
            else int(
                getattr(
                    self.settings,
                    "hybrid_prefilter_pool_limit",
                    self.settings.hybrid_rerank_limit,
                )
            ),
        )
        if detailed_trace and hasattr(self.retriever, "search_with_trace"):
            wide_candidates, retriever_debug = self.retriever.search_with_trace(
                retrieval_query,
                pool_limit,
                canonical_query=canonical_query,
            )
            query_interpretation["retrieval_trace"]["retriever"] = retriever_debug
        else:
            wide_candidates = self.retriever.search(
                retrieval_query,
                pool_limit,
                canonical_query=canonical_query,
            )

        candidates, prefilter_debug = self.selection.technical_prefilter_candidates(
            wide_candidates,
            soft_constraints=soft_constraints,
            hard_constraints=hard_constraints,
            limit=self.settings.hybrid_rerank_limit,
        )
        query_interpretation["retrieval_trace"]["technical_prefilter"] = prefilter_debug
        self.telemetry.log_match_trace(
            "retrieval_completed",
            enabled=bool(getattr(self.settings, "match_trace_enabled", True)),
            strategy=retrieval_strategy,
            candidate_count=len(candidates),
            prefilter_pool_count=len(wide_candidates),
            retrieval_query=trim_text(retrieval_query, 500),
            alternate_query=trim_text(canonical_query, 500),
        )
        reranking = CandidateRerankingService(
            settings=self.settings,
            reranker=self.reranker,
            candidate_selection=self.selection,
            second_chance=second_chance,
        )
        rerank_query = (
            retrieval_query
            if retrieval_strategy
            in {
                "web_enriched_technical_plus_catalog",
                "competitor_decoded_technical_plus_catalog",
                "competitor_resolved_technical_plus_catalog",
            }
            else query
        )
        return reranking.rerank_candidates(
            query,
            candidates,
            constraints=hard_constraints,
            query_interpretation=query_interpretation,
            rerank_query=rerank_query,
        )
