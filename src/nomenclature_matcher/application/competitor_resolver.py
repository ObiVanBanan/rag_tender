from __future__ import annotations

from typing import Any

from ..domain.competitor import (
    FACT_FIELDS,
    CompetitorResolution,
    ResolvedFact,
    compact_identity,
    merge_fact,
)
from ..domain.query_signals import exact_product_identity_anchors
from .ports import CatalogRegistryPort, CompetitorKnowledgeStorePort


class CompetitorResolver:
    def __init__(
        self,
        *,
        store: CompetitorKnowledgeStorePort,
        registry: CatalogRegistryPort,
    ) -> None:
        self.store = store
        self.registry = registry

    def resolve(self, query: str) -> CompetitorResolution:
        cached = self.store.find(query)
        if cached is not None:
            return cached

        catalog = self.registry.resolve(query)
        if catalog is not None and catalog.resolved:
            self.store.put(catalog)
            return catalog

        return CompetitorResolution(
            status="MISS",
            manufacturer=self.registry.manufacturer_for_query(query),
        )

    @staticmethod
    def _page_contains_exact_anchor(page: dict[str, Any], anchor: str) -> bool:
        haystack = compact_identity(
            " ".join(
                [
                    str(page.get("target") or ""),
                    str(page.get("text") or ""),
                ]
            )
        )
        return bool(anchor and anchor in haystack)

    def web_context_is_exact(
        self,
        query: str,
        lookup_debug: dict[str, Any] | None,
    ) -> bool:
        debug = lookup_debug or {}
        exact_anchors = exact_product_identity_anchors(query)
        pages = [p for p in (debug.get("pages") or []) if isinstance(p, dict)]
        if not exact_anchors or not pages:
            return False
        return any(
            self._page_contains_exact_anchor(page, anchor)
            for anchor in exact_anchors
            for page in pages
        )

    def learn_from_web(
        self,
        query: str,
        attributes: dict[str, Any],
        lookup_debug: dict[str, Any] | None,
    ) -> CompetitorResolution | None:
        debug = lookup_debug or {}
        if not debug.get("accepted") or not debug.get("identity_verified"):
            return None

        exact_anchors = exact_product_identity_anchors(query)
        pages = [p for p in (debug.get("pages") or []) if isinstance(p, dict)]
        if not exact_anchors or not pages:
            return None

        verified_anchor = None
        verified_pages: list[dict[str, Any]] = []
        for anchor in exact_anchors:
            matching = [
                page
                for page in pages
                if self._page_contains_exact_anchor(page, anchor)
            ]
            if matching:
                verified_anchor = anchor
                verified_pages = matching
                break

        # Family-only search results may be useful for interactive context, but
        # must never be persisted as an exact ProductRecord.
        if verified_anchor is None:
            return None

        manufacturer = self.registry.manufacturer_for_query(query)
        sources = [
            {
                "url": page.get("target"),
                "source_type": "web_exact_product",
                "identity_level": "EXACT_PRODUCT",
                "evidence_text": str(page.get("text") or "")[:800],
            }
            for page in verified_pages
            if page.get("target")
        ]
        if not sources:
            return None

        existing = self.store.find(query)
        facts = dict(existing.facts or {}) if existing is not None else {}
        for field, value in attributes.items():
            if field not in FACT_FIELDS or value is None:
                continue
            facts[field] = merge_fact(
                facts.get(field),
                ResolvedFact(value, "SUPPORTED", sources),
            )

        if not facts:
            return None

        aliases = list(existing.aliases) if existing is not None else []
        aliases.append(verified_anchor)
        if manufacturer:
            aliases.append(f"{manufacturer} {verified_anchor}")

        resolution = CompetitorResolution(
            status="WEB_LEARNED",
            identity_key=(
                existing.identity_key
                if existing is not None and existing.identity_key
                else f"{(manufacturer or 'unknown').casefold()}:{verified_anchor}"
            ),
            identity_anchor=(
                existing.identity_anchor
                if existing is not None and existing.identity_anchor
                else verified_anchor
            ),
            identity_level="EXACT_PRODUCT",
            manufacturer=(
                existing.manufacturer
                if existing is not None and existing.manufacturer
                else manufacturer
            ),
            article=(
                existing.article
                if existing is not None and existing.article
                else verified_anchor
            ),
            aliases=tuple(dict.fromkeys(alias for alias in aliases if alias)),
            facts=facts,
        )
        self.store.put(resolution)
        return resolution
