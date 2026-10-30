from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


FACT_FIELDS = {
    "product_type",
    "dn",
    "pn_min_mpa",
    "joining_type",
    "thread_type",
    "working_medium",
    "valve_type",
    "body_material",
    "body_material_grade",
    "bore_type",
    "control",
}


def compact_identity(value: str) -> str:
    return re.sub(
        r"[^0-9a-zа-я]+",
        "",
        str(value or "").lower().replace("ё", "е"),
        flags=re.IGNORECASE,
    )


@dataclass(frozen=True)
class ResolvedFact:
    value: Any
    status: str
    sources: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "status": self.status,
            "sources": list(self.sources),
        }


@dataclass(frozen=True)
class CompetitorResolution:
    status: str
    identity_key: str | None = None
    identity_anchor: str | None = None
    identity_level: str = "UNRESOLVED"
    manufacturer: str | None = None
    article: str | None = None
    aliases: tuple[str, ...] = ()
    facts: dict[str, ResolvedFact] | None = None

    @property
    def resolved(self) -> bool:
        return bool(
            self.identity_level == "EXACT_PRODUCT"
            and self.identity_key
            and self.identity_anchor
            and self.facts
        )

    def attributes(self) -> dict[str, Any]:
        return {
            field: fact.value
            for field, fact in (self.facts or {}).items()
            if fact.status in {"VERIFIED", "SUPPORTED"} and fact.value is not None
        }

    def prompt_context(self) -> dict[str, Any] | None:
        if not self.resolved:
            return None
        return {
            "source": "competitor_resolver",
            "resolution_status": self.status,
            "identity_key": self.identity_key,
            "identity_anchor": self.identity_anchor,
            "identity_level": self.identity_level,
            "manufacturer": self.manufacturer,
            "article": self.article,
            "canonical_profile": {
                "facts": {
                    field: fact.as_dict()
                    for field, fact in sorted((self.facts or {}).items())
                }
            },
        }

    def debug_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "resolved": self.resolved,
            "identity_key": self.identity_key,
            "identity_anchor": self.identity_anchor,
            "identity_level": self.identity_level,
            "manufacturer": self.manufacturer,
            "article": self.article,
            "aliases": list(self.aliases),
            "facts": {
                field: fact.as_dict()
                for field, fact in sorted((self.facts or {}).items())
            },
        }


def merge_fact(
    existing: ResolvedFact | None,
    incoming: ResolvedFact,
) -> ResolvedFact:
    if existing is None:
        return incoming

    sources = list(existing.sources)
    for source in incoming.sources:
        if source not in sources:
            sources.append(source)

    if existing.value == incoming.value:
        status = (
            "VERIFIED"
            if "VERIFIED" in {existing.status, incoming.status}
            else "SUPPORTED"
        )
        return ResolvedFact(existing.value, status, sources)

    if existing.status == "VERIFIED":
        return ResolvedFact(existing.value, "VERIFIED", sources)

    return ResolvedFact(None, "CONFLICTED", sources)
