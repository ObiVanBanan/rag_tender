from dataclasses import replace
from typing import Any

from .application.query_preparation import QueryPreparationService
from .application.candidate_selection import CandidateSelectionService
from .application.candidate_reranking import CandidateRerankingService
from .application.second_chance import SecondChanceCandidateRetriever
from .application.hybrid_candidate_search import HybridCandidateSearchService
from .application.ports import (
    CompetitorLookupPort,
    CompetitorResolverPort,
    DenseStorePort,
    EmbedderPort,
    HybridRetrieverPort,
    QueryInterpreterPort,
    RerankerPort,
    TelemetryPort,
)
from .application.telemetry import NullTelemetry
from .domain.product import LDProduct
from .models import MatchResult, SearchCandidate, SelectedMatch
from .query_canonicalization import canonicalize_retrieval_query


class NomenclatureMatcher:
    def __init__(
        self,
        embedder: EmbedderPort,
        store: DenseStorePort,
        settings: Any,
        reranker: RerankerPort | None = None,
        hybrid_retriever: HybridRetrieverPort | None = None,
        query_interpreter: QueryInterpreterPort | None = None,
        competitor_lookup: CompetitorLookupPort | None = None,
        competitor_resolver: CompetitorResolverPort | None = None,
        telemetry: TelemetryPort | None = None,
    ):
        self.embedder = embedder
        self.store = store
        self.settings = settings
        self.telemetry = telemetry or NullTelemetry()
        self.candidate_selection = CandidateSelectionService()
        self.reranker = reranker
        self.hybrid_retriever = hybrid_retriever
        self.query_interpreter = query_interpreter
        self.competitor_lookup = competitor_lookup
        self.competitor_resolver = competitor_resolver
        self.query_preparation = QueryPreparationService(
            settings=settings,
            interpreter=self.query_interpreter,
            competitor_lookup=self.competitor_lookup,
            competitor_resolver=self.competitor_resolver,
            telemetry=self.telemetry,
        )

    def _normalize_query(self, query: str) -> str:
        return " ".join(query.split())

    def _search_candidates(self, query: str, limit: int) -> list[SearchCandidate]:
        hits = self.store.search(self.embedder.embed_query(query), limit)
        return [
            SearchCandidate(
                ld_id=int(hit.payload["ld_id"]),
                name=hit.payload.get("name", ""),
                article=hit.payload.get("article"),
                score=float(hit.score),
                price=hit.payload.get("price"),
                dn=hit.payload.get("dn"),
                pn=hit.payload.get("pn"),
                joining_type=hit.payload.get("joining_type"),
                url=hit.payload.get("url"),
                properties=hit.payload.get("properties"),
                search_text=hit.payload.get("search_text"),
                dense_score=float(hit.score),
                dense_rank=index,
                retrieval_sources=["dense"],
            )
            for index, hit in enumerate(hits, 1)
        ]

    @staticmethod
    def _candidate_as_product(candidate: SearchCandidate) -> LDProduct:
        return CandidateSelectionService.candidate_as_product(candidate)

    def _eligible_candidates(
        self,
        candidates: list[SearchCandidate],
        constraints: dict,
    ) -> list[tuple[int, SearchCandidate]]:
        return self.candidate_selection.eligible_candidates(candidates, constraints)

    def _technical_prefilter_candidates(
        self,
        candidates: list[SearchCandidate],
        *,
        soft_constraints: dict | None,
        hard_constraints: dict | None,
        limit: int,
    ) -> tuple[list[SearchCandidate], dict]:
        return self.candidate_selection.technical_prefilter_candidates(
            candidates,
            soft_constraints=soft_constraints,
            hard_constraints=hard_constraints,
            limit=limit,
        )

    def _second_chance_candidates(
        self,
        constraints: dict,
    ) -> tuple[list[SearchCandidate], list[tuple[int, SearchCandidate]], dict | None] | None:
        retriever = SecondChanceCandidateRetriever(
            retriever=self.hybrid_retriever,
            settings=self.settings,
            candidate_selection=self.candidate_selection,
        )
        return retriever.retrieve(constraints)

    def _build_selected_match(
        self,
        candidate: SearchCandidate,
        item,
        *,
        candidate_id: int | None = None,
    ) -> SelectedMatch:
        return CandidateRerankingService._build_selected_match(
            candidate, item, candidate_id=candidate_id
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
        service = CandidateRerankingService(
            settings=self.settings,
            reranker=self.reranker,
            candidate_selection=self.candidate_selection,
            second_chance=self._second_chance_candidates,
        )
        return service.rerank_candidates(
            query,
            candidates,
            constraints=constraints,
            query_interpretation=query_interpretation,
            rerank_query=rerank_query,
        )

    def match_one(self, query: str) -> MatchResult:
        query = self._normalize_query(query)
        if not query:
            return MatchResult(query=query, status="NOT_FOUND")
        candidates = self._search_candidates(query, self.settings.match_top_k)
        best = candidates[0] if candidates else None
        status = "MATCHED" if best and best.score >= self.settings.match_score_threshold else "NOT_FOUND"
        return MatchResult(query=query, status=status, score=best.score if best else None, ld_product=best if status == "MATCHED" else None, candidates=candidates)

    def match_one_with_rerank(self, query: str) -> MatchResult:
        query = self._normalize_query(query)
        if not query:
            return MatchResult(query=query, status="NOT_FOUND")
        candidates = self._search_candidates(query, self.settings.rerank_candidate_limit)
        return self.rerank_candidates(query, candidates)

    @staticmethod
    def _hard_constraints(query: str, pre_interpretation, enriched_interpretation=None) -> dict:
        from .application.query_policy import hard_constraints

        return hard_constraints(query, pre_interpretation, enriched_interpretation)

    def match_one_hybrid_with_rerank(self, query: str) -> MatchResult:
        query = self._normalize_query(query)
        if not query:
            return MatchResult(query=query, status="NOT_FOUND")
        if self.hybrid_retriever is None:
            raise ValueError("Hybrid retriever is not configured")

        if self.query_interpreter is not None:
            prepared = self.query_preparation.prepare(query)
            if isinstance(prepared, MatchResult):
                return prepared
            search = HybridCandidateSearchService(
                settings=self.settings,
                retriever=self.hybrid_retriever,
                reranker=self.reranker,
                telemetry=self.telemetry,
            )
            return search.execute(
                query=query,
                retrieval_query=prepared.retrieval_query,
                canonical_query=prepared.canonical_query,
                retrieval_strategy=prepared.retrieval_strategy,
                soft_constraints=prepared.interpretation.constraints.model_dump(),
                hard_constraints=prepared.hard_constraints,
                query_interpretation=prepared.interpretation_payload,
                second_chance=self._second_chance_candidates,
                prefilter_pool_limit=getattr(
                    self.settings,
                    "hybrid_prefilter_pool_limit",
                    200
                    if prepared.source_decode is not None
                    else self.settings.hybrid_rerank_limit,
                ),
            )

        canonicalization = canonicalize_retrieval_query(query)
        candidates = self.hybrid_retriever.search(
            query,
            self.settings.hybrid_rerank_limit,
            canonical_query=canonicalization.canonical_query,
        )
        return self.rerank_candidates(query, candidates)

    def _match_many_with(self, queries: list[str], match_one) -> list[MatchResult]:
        cache = {}
        for query in queries:
            normalized = self._normalize_query(query)
            if normalized and normalized not in cache:
                cache[normalized] = match_one(normalized)
        return [
            replace(cache[normalized], query=query)
            if (normalized := self._normalize_query(query)) and normalized in cache
            else MatchResult(query=query, status="NOT_FOUND")
            for query in queries
        ]

    def match_many(self, queries: list[str]) -> list[MatchResult]:
        return self._match_many_with(queries, self.match_one)

    def match_many_hybrid_with_rerank(self, queries: list[str]) -> list[MatchResult]:
        return self._match_many_with(queries, self.match_one_hybrid_with_rerank)

    match = match_many
