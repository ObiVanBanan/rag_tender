"""CSV-first, native RAG fallback. Never mix independent evidence sources.

Known CSV matches are returned immediately. An absent/technically rejected
CSV match is searched using the existing unchanged production RAG pipeline.
Ambiguous 11B27P inputs remain guarded by the common safety gate and are not
sent to a paid LLM. Exceptions from RAG are intentionally NOT converted to
"not found" because that would misrepresent a provider outage as a negative.
"""
from __future__ import annotations

from dataclasses import replace

from .csv_mapping import CsvMappingMatcher
from .models import MatchResult


class CsvFirstRagMatcher:
    def __init__(self, settings, rag_matcher, csv_matcher=None):
        self.settings = settings
        self.csv_matcher = csv_matcher or CsvMappingMatcher(settings)
        self.rag_matcher = rag_matcher
        # Required by the existing business-demo correction/append handlers.
        self.index = self.csv_matcher.index
        # Required by ProductionRuntime.close() for web MCP clean shutdown.
        self.competitor_lookup = getattr(rag_matcher, "competitor_lookup", None)

    def match_one_hybrid_with_rerank(self, query: str) -> MatchResult:
        csv = self.csv_matcher.match_one_hybrid_with_rerank(query)
        if csv.status != "NOT_FOUND":
            return csv
        # A CSV miss includes no candidates (a rejected mapping is also a miss).
        # Keep the original, unmodified tender query for normal RAG processing.
        rag = self.rag_matcher.match_one_hybrid_with_rerank(query)
        interpretation = rag.query_interpretation
        if not isinstance(interpretation, dict):
            interpretation = {}
        # Do not mutate the nested RAG matcher's result or lose its constraints.
        return replace(rag, query_interpretation={
            **interpretation,
            "csv_fallback": True,
            "csv_fallback_reason": csv.reason,
        })
