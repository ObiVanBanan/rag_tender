from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..domain.competitor import FACT_FIELDS, CompetitorResolution, ResolvedFact, compact_identity
from ..domain.query_signals import exact_product_identity_anchors


class CatalogRegistry:
    """Curated source registry plus data-driven manufacturer catalog schemas."""

    def __init__(self, path: str | Path):
        try:
            self.payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.payload = {
                "manufacturers": [],
                "products": [],
                "catalog_schemas": [],
            }

    def manufacturer_for_query(self, query: str) -> str | None:
        text = " ".join(str(query or "").lower().replace("ё", "е").split())
        for item in self.payload.get("manufacturers", []):
            for alias in item.get("aliases", []):
                token = str(alias).lower().replace("ё", "е")
                if re.search(
                    rf"(?<![0-9a-zа-я]){re.escape(token)}(?![0-9a-zа-я])",
                    text,
                ):
                    return item.get("name")
        return None

    @staticmethod
    def _source(product_or_rule: dict[str, Any]) -> dict[str, Any]:
        source = dict(product_or_rule.get("source") or {})
        source.setdefault("identity_level", "EXACT_PRODUCT")
        return source

    @staticmethod
    def _facts_from_values(
        values: dict[str, Any],
        source: dict[str, Any],
    ) -> dict[str, ResolvedFact]:
        return {
            field: ResolvedFact(
                value=value,
                status="VERIFIED" if value is not None else "UNKNOWN",
                sources=[source],
            )
            for field, value in values.items()
            if field in FACT_FIELDS
        }

    def _resolve_curated_product(
        self,
        query: str,
        anchors: set[str],
    ) -> CompetitorResolution | None:
        matches: list[tuple[int, dict[str, Any], str]] = []
        for product in self.payload.get("products", []):
            for alias in product.get("aliases", []):
                token = compact_identity(alias)
                if token in anchors:
                    matches.append((len(token), product, token))

        if not matches:
            return None

        best = max(score for score, _, _ in matches)
        winners = [(product, token) for score, product, token in matches if score == best]
        if len({product.get("identity_key") for product, _ in winners}) != 1:
            return None

        product, anchor = winners[0]
        source = self._source(product)
        facts = self._facts_from_values(product.get("facts") or {}, source)
        return CompetitorResolution(
            status="CATALOG_RESOLVED",
            identity_key=product.get("identity_key"),
            identity_anchor=anchor,
            identity_level="EXACT_PRODUCT",
            manufacturer=product.get("manufacturer"),
            article=product.get("article") or anchor,
            aliases=tuple(product.get("aliases", [])),
            facts=facts,
        )

    @staticmethod
    def _pn_for_dn(rule: dict[str, Any], dn: int) -> float | None:
        if rule.get("pn_min_mpa") is not None:
            return float(rule["pn_min_mpa"])
        for item in rule.get("pn_rules", []):
            min_dn = int(item.get("min_dn", 0))
            max_dn = int(item.get("max_dn", 10**9))
            if min_dn <= dn <= max_dn:
                return float(item["pn_min_mpa"])
        return None

    @staticmethod
    def _extract_designation_value(
        groups: dict[str, str | None],
        spec: dict[str, Any],
    ) -> Any:
        group = str(spec.get("group") or "")
        raw = groups.get(group)
        if raw is None:
            return spec.get("default")

        value = str(raw)
        regex_map = spec.get("regex_map") or []
        if regex_map:
            for rule in regex_map:
                if re.search(str(rule.get("regex") or ""), value, re.IGNORECASE):
                    return rule.get("value")
            return spec.get("default")

        mapping = spec.get("map")
        if isinstance(mapping, dict):
            return mapping.get(value, mapping.get(value.upper(), spec.get("default")))

        kind = spec.get("type")
        if kind == "int":
            return int(value)
        if kind == "float_div":
            return float(value.replace(",", ".")) / float(spec.get("divisor", 1))
        if kind == "compact":
            return compact_identity(value)
        return value

    def _resolve_designation_schema(
        self,
        query: str,
        anchors: set[str],
    ) -> CompetitorResolution | None:
        manufacturer = self.manufacturer_for_query(query)
        if manufacturer is None:
            return None

        for schema in self.payload.get("designation_schemas", []):
            if str(schema.get("manufacturer") or "").casefold() != manufacturer.casefold():
                continue

            pattern = re.compile(str(schema.get("query_regex") or ""), re.IGNORECASE)
            match = pattern.search(query)
            if match is None:
                continue

            groups = match.groupdict()
            identity_group = str(schema.get("identity_group") or "model")
            identity_raw = groups.get(identity_group)
            if identity_raw is None:
                continue
            identity_anchor = compact_identity(identity_raw)
            if identity_anchor not in anchors:
                continue

            values: dict[str, Any] = dict(schema.get("fixed_facts") or {})
            for field, spec in (schema.get("field_extractors") or {}).items():
                if field not in FACT_FIELDS or not isinstance(spec, dict):
                    continue
                values[field] = self._extract_designation_value(groups, spec)

            for rule in schema.get("query_fact_rules", []):
                if re.search(str(rule.get("regex") or ""), query, re.IGNORECASE):
                    for field, value in (rule.get("facts") or {}).items():
                        if field in FACT_FIELDS:
                            values[field] = value

            source = self._source(schema)
            source["evidence_text"] = (
                f"Catalog designation schema {manufacturer}; exact model "
                f"{identity_raw}; extracted groups={groups}."
            )
            facts = self._facts_from_values(values, source)
            aliases = (identity_anchor, f"{manufacturer} {identity_anchor}")
            return CompetitorResolution(
                status="CATALOG_DESIGNATION_RESOLVED",
                identity_key=f"{manufacturer.casefold()}:{identity_anchor}",
                identity_anchor=identity_anchor,
                identity_level="EXACT_PRODUCT",
                manufacturer=manufacturer,
                article=str(identity_raw),
                aliases=aliases,
                facts=facts,
            )

        return None

    def _resolve_catalog_schema(
        self,
        query: str,
        anchors: set[str],
    ) -> CompetitorResolution | None:
        manufacturer = self.manufacturer_for_query(query)
        if manufacturer is None:
            return None

        for schema in self.payload.get("catalog_schemas", []):
            if str(schema.get("manufacturer") or "").casefold() != manufacturer.casefold():
                continue

            pattern = re.compile(str(schema.get("article_regex") or ""))
            for anchor in sorted(anchors, key=len, reverse=True):
                match = pattern.fullmatch(anchor)
                if match is None:
                    continue

                groups = match.groupdict()
                series = groups.get("series")
                material_code = groups.get("material")
                dn_text = groups.get("dn")
                if not series or not dn_text:
                    continue

                rule = (schema.get("series_rules") or {}).get(series)
                if not isinstance(rule, dict):
                    continue

                dn = int(dn_text)
                pn = self._pn_for_dn(rule, dn)
                material_map = schema.get("material_codes") or {}
                material_grade = material_map.get(material_code)

                values: dict[str, Any] = {
                    "product_type": rule.get("product_type", "ball_valve"),
                    "dn": dn,
                    "pn_min_mpa": pn,
                    "joining_type": rule.get("joining_type"),
                    "bore_type": rule.get("bore_type"),
                    "body_material": rule.get("body_material", "steel"),
                    "body_material_grade": material_grade,
                }
                for field in ("thread_type", "working_medium", "valve_type", "control"):
                    if field in rule:
                        values[field] = rule.get(field)

                source = self._source(rule)
                source["evidence_text"] = (
                    f"Catalog schema {manufacturer} series {series}; exact article "
                    f"{anchor}; DN={dn}; PN={pn}; material code={material_code}."
                )
                facts = self._facts_from_values(values, source)
                aliases = (anchor, f"{manufacturer} {anchor}")
                return CompetitorResolution(
                    status="CATALOG_SCHEMA_RESOLVED",
                    identity_key=f"{manufacturer.casefold()}:{anchor}",
                    identity_anchor=anchor,
                    identity_level="EXACT_PRODUCT",
                    manufacturer=manufacturer,
                    article=anchor,
                    aliases=aliases,
                    facts=facts,
                )

        return None

    def resolve(self, query: str) -> CompetitorResolution | None:
        anchors = set(exact_product_identity_anchors(query))
        if not anchors:
            return None

        curated = self._resolve_curated_product(query, anchors)
        if curated is not None:
            return curated

        designation = self._resolve_designation_schema(query, anchors)
        if designation is not None:
            return designation

        return self._resolve_catalog_schema(query, anchors)
