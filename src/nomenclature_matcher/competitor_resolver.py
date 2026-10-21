"""Compatibility exports for the layered competitor resolver."""

from .application.competitor_resolver import CompetitorResolver
from .domain.competitor import (
    FACT_FIELDS,
    CompetitorResolution,
    ResolvedFact,
    compact_identity,
    merge_fact,
)
from .infrastructure.competitor_catalog_registry import CatalogRegistry
from .infrastructure.competitor_knowledge_store import CompetitorKnowledgeStore

_compact = compact_identity
_merge_fact = merge_fact


class LegacyCompetitorResolver(CompetitorResolver):
    """Settings-based constructor retained for existing integrations."""

    def __init__(self, settings, *, store=None, registry=None):
        store = store or CompetitorKnowledgeStore(
            getattr(settings, "competitor_kb_path", ".rag_tender/competitor_kb.sqlite3")
        )
        registry = registry or CatalogRegistry(
            getattr(
                settings,
                "competitor_catalog_registry_path",
                "data/competitor_catalogs/sources.json",
            )
        )
        super().__init__(store=store, registry=registry)


# Keep the historical settings-based API under its original public name.
CompetitorResolver = LegacyCompetitorResolver

__all__ = [
    "FACT_FIELDS", "CatalogRegistry", "CompetitorKnowledgeStore",
    "CompetitorResolution", "CompetitorResolver", "ResolvedFact",
    "compact_identity", "merge_fact",
]
