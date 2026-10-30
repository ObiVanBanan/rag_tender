from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from ..models import MatchResult, RerankResult, SearchCandidate

if TYPE_CHECKING:
    from ..competitor_decoding import CompetitorDecode
    from ..domain.competitor import CompetitorResolution
    from ..query_interpreter import QueryInterpretation
    from ..web_search_mcp import WebSearchLookupResult


class MatcherPort(Protocol):
    settings: Any
    telemetry: TelemetryPort

    def match_one_hybrid_with_rerank(self, query: str) -> MatchResult: ...


class TelemetryPort(Protocol):
    def log_match_trace(self, stage: str, *, enabled: bool = True, **payload: Any) -> None: ...

    def log_operational_event(
        self, event: str, summary: str, *, severity: str = "INFO", **payload: Any
    ) -> None: ...

    def record_match_item(self, status: str, duration_seconds: float) -> None: ...

    def record_match_decision(self, status: str, reason: str | None) -> str: ...

    def record_web_enrichment(self, status: str, duration_seconds: float) -> None: ...

    def record_enrichment_gate(self, reason: str) -> None: ...

    def record_attribute_conflicts(self, fields: list[str]) -> None: ...

    def record_history_write(self, status: str, duration_seconds: float) -> None: ...

    def record_api_error(self, error_type: str) -> None: ...

    def set_item_index(self, item_index: int | None) -> Any: ...

    def reset_item_index(self, token: Any) -> None: ...


class EmbedderPort(Protocol):
    def embed_query(self, text: str) -> list[float]: ...


class DenseStorePort(Protocol):
    def search(self, vector: list[float], limit: int) -> list[Any]: ...


class HybridRetrieverPort(Protocol):
    def search(
        self,
        query: str,
        limit: int | None = None,
        canonical_query: str | None = None,
    ) -> list[SearchCandidate]: ...


class RerankerPort(Protocol):
    def rerank(
        self,
        query: str,
        candidates: list[SearchCandidate],
        constraints: dict[str, Any] | None = None,
    ) -> RerankResult: ...


SecondChanceResult = tuple[
    list[SearchCandidate],
    list[tuple[int, SearchCandidate]],
    dict[str, Any] | None,
]


class QueryInterpreterPort(Protocol):
    def interpret(
        self,
        query: str,
        *,
        competitor_context: dict[str, Any] | None = None,
    ) -> QueryInterpretation: ...


class CompetitorLookupPort(Protocol):
    def lookup(self, query: str) -> WebSearchLookupResult: ...


class CompetitorResolverPort(Protocol):
    def resolve(self, query: str) -> CompetitorResolution: ...

    def web_context_is_exact(self, query: str, debug: dict[str, Any] | None) -> bool: ...

    def learn_from_web(
        self,
        query: str,
        constraints: dict[str, Any],
        debug: dict[str, Any] | None,
    ) -> CompetitorResolution | None: ...


class CompetitorKnowledgeStorePort(Protocol):
    def find(self, query: str) -> CompetitorResolution | None: ...

    def put(self, resolution: CompetitorResolution) -> None: ...


class CatalogRegistryPort(Protocol):
    def resolve(self, query: str) -> CompetitorResolution | None: ...

    def manufacturer_for_query(self, query: str) -> str | None: ...


class RequestHistoryPort(Protocol):
    def open(self) -> None: ...

    def ping(self) -> bool: ...

    def record(self, **kwargs: Any) -> None: ...

    def close(self) -> None: ...


class CollectionReadinessPort(Protocol):
    def collection_exists(self, name: str) -> bool: ...


class ResourceScopePort(Protocol):
    def close(self) -> None: ...
