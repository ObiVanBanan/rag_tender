"""Prepare an interpreted query and safe retrieval plan for hybrid matching."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING, Any

from ..competitor_decoding import decode_competitor_query
from ..models import MatchResult
from ..query_canonicalization import build_constraint_rendered_query
from .diagnostics import build_attribute_diagnostic, trim_text
from .ports import (
    CompetitorLookupPort,
    CompetitorResolverPort,
    QueryInterpreterPort,
    TelemetryPort,
)
from .query_policy import enrichment_gate, hard_constraints, apply_verified_catalog_constraints
from .telemetry import NullTelemetry

if TYPE_CHECKING:
    from ..competitor_decoding import CompetitorDecode
    from ..domain.competitor import CompetitorResolution
    from ..query_interpreter import QueryInterpretation


@dataclass(frozen=True)
class PreparedQuery:
    interpretation: QueryInterpretation
    pre_interpretation: QueryInterpretation
    enriched_interpretation: QueryInterpretation | None
    source_decode: CompetitorDecode | None
    competitor_resolution: CompetitorResolution | None
    hard_constraints: dict[str, Any]
    interpretation_payload: dict[str, Any]
    retrieval_query: str
    canonical_query: str | None
    retrieval_strategy: str


class QueryPreparationService:
    """Own resolver, interpretation, enrichment, and retrieval-plan policy."""

    def __init__(
        self,
        *,
        settings: Any,
        interpreter: QueryInterpreterPort,
        competitor_lookup: CompetitorLookupPort | None = None,
        competitor_resolver: CompetitorResolverPort | None = None,
        telemetry: TelemetryPort | None = None,
    ) -> None:
        self.settings = settings
        self.interpreter = interpreter
        self.competitor_lookup = competitor_lookup
        self.competitor_resolver = competitor_resolver
        self.telemetry = telemetry or NullTelemetry()

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.split())

    def _interpret(
        self,
        query: str,
        competitor_context: dict[str, Any] | None = None,
    ) -> QueryInterpretation:
        if competitor_context is None:
            return self.interpreter.interpret(query)
        return self.interpreter.interpret(query, competitor_context=competitor_context)

    def _lookup_competitor(self, query: str):
        if self.competitor_lookup is None:
            return None, None, None
        started = perf_counter()
        trace_enabled = bool(getattr(self.settings, "match_trace_enabled", True))
        self.telemetry.log_match_trace("web_enrichment_started", enabled=trace_enabled)
        try:
            result = self.competitor_lookup.lookup(query)
        except Exception as exc:  # enrichment must never break matching
            duration = perf_counter() - started
            self.telemetry.record_web_enrichment("error", duration)
            debug = {
                "attempted": True,
                "accepted": False,
                "reason": f"lookup_error:{type(exc).__name__}:{exc}",
                "search_results": "",
                "pages": [],
                "duration_ms": round(duration * 1000, 3),
            }
            self.telemetry.log_match_trace(
                "web_enrichment_failed",
                enabled=trace_enabled,
                duration_ms=debug["duration_ms"],
                error_type=type(exc).__name__,
            )
            return None, None, debug

        duration = perf_counter() - started
        debug = result.debug_payload()
        accepted = bool(debug.get("accepted", getattr(result, "accepted", False)))
        status = "accepted" if accepted else "rejected"
        self.telemetry.record_web_enrichment(status, duration)
        debug["accepted"] = accepted
        debug["duration_ms"] = round(duration * 1000, 3)
        self.telemetry.log_match_trace(
            "web_enrichment_completed",
            enabled=trace_enabled,
            duration_ms=debug["duration_ms"],
            status=status,
            reason=trim_text(debug.get("reason"), 120),
            page_count=len(debug.get("pages") or []),
        )
        return result, result.prompt_context(), debug

    def _log_enrichment_diagnostic(self, query: str, debug: dict) -> None:
        pages = debug.get("pages") or []
        reason = trim_text(debug.get("reason"), 220)
        accepted = bool(debug.get("accepted"))
        attempted = bool(debug.get("attempted"))
        duration_ms = debug.get("duration_ms")
        if not attempted:
            status, severity = "SKIPPED", "INFO"
        elif accepted:
            status, severity = "ACCEPTED", "INFO"
        elif str(reason).startswith("lookup_error") or "error" in str(reason).lower():
            status, severity = "ERROR", "ERROR"
        else:
            status, severity = "REJECTED", "WARNING"

        summary = f"WEB {status}"
        if reason:
            summary += f" — {reason}"
        if duration_ms is not None:
            summary += f" ({duration_ms:.0f} ms)"
        evidence_preview = [
            {"target": trim_text(page.get("target"), 300), "text": trim_text(page.get("text"), 500)}
            for page in pages[:2]
            if isinstance(page, dict)
        ]
        self.telemetry.log_operational_event(
            "web_enrichment_diagnostic",
            summary,
            severity=severity,
            input_query=trim_text(query, 500),
            attempted=attempted,
            accepted=accepted,
            reason=reason,
            duration_ms=duration_ms,
            search_query=trim_text(debug.get("search_query"), 500),
            page_count=len(pages),
            search_results_preview=trim_text(debug.get("search_results"), 700),
            evidence_preview=evidence_preview,
        )

    def _log_attribute_diagnostic(
        self,
        query: str,
        *,
        pre_interpretation,
        interpretation,
        hard: dict,
    ) -> None:
        before = pre_interpretation.constraints.model_dump()
        after = interpretation.constraints.model_dump()
        diagnostic = build_attribute_diagnostic(before, after, hard)
        conflicts = diagnostic["hard_conflict_fields"]
        self.telemetry.record_attribute_conflicts(conflicts)
        changed = diagnostic["changed_fields"]
        summary = "changed: " + ", ".join(changed) if changed else "attributes unchanged"
        if conflicts:
            summary += " | HARD CONFLICT: " + ", ".join(conflicts)
        self.telemetry.log_operational_event(
            "attribute_diagnostic",
            summary,
            severity="WARNING" if conflicts else "INFO",
            input_query=trim_text(query, 500),
            changed_fields=changed,
            hard_conflict_fields=conflicts,
            hard_conflicts=diagnostic["hard_conflicts"],
            attributes_before_web=before,
            attributes_after_web=after,
            hard_constraints=hard,
        )

    def prepare(self, query: str) -> PreparedQuery | MatchResult:
        source_decode = (
            decode_competitor_query(query)
            if getattr(self.settings, "competitor_decoder_baseline_enabled", False)
            else None
        )
        competitor_resolution = None
        resolver_context = None
        if self.competitor_resolver is not None and source_decode is None:
            try:
                competitor_resolution = self.competitor_resolver.resolve(query)
                resolver_context = competitor_resolution.prompt_context()
            except Exception as exc:
                self.telemetry.log_match_trace(
                    "competitor_resolver_failed",
                    enabled=bool(getattr(self.settings, "match_trace_enabled", True)),
                    error_type=type(exc).__name__,
                )

        try:
            pre = self._interpret(query, competitor_context=resolver_context)
        except Exception as exc:
            return MatchResult(
                query=query,
                status="RERANK_FAILED",
                reason=f"QUERY_INTERPRET_FAILED: {type(exc).__name__}: {exc}",
            )

        interpretation = pre
        enriched = None
        lookup_debug = None
        should_enrich, gate_reason = enrichment_gate(
            query, pre, lookup_enabled=self.competitor_lookup is not None
        )
        if competitor_resolution is not None and competitor_resolution.resolved:
            should_enrich, gate_reason = False, "competitor_resolver_resolved"
        self.telemetry.record_enrichment_gate(gate_reason)

        if should_enrich:
            _, context, lookup_debug = self._lookup_competitor(query)
            if (
                context is not None
                and self.competitor_resolver is not None
                and not self.competitor_resolver.web_context_is_exact(query, lookup_debug)
            ):
                context = None
                if lookup_debug is not None:
                    lookup_debug["resolver_identity_gate"] = "rejected"
                    lookup_debug["resolver_identity_reason"] = (
                        "exact_product_anchor_not_found_in_fetched_pages"
                    )
            if context is not None:
                try:
                    enriched = self._interpret(query, competitor_context=context)
                    interpretation = enriched
                    if self.competitor_resolver is not None and source_decode is None:
                        learned = self.competitor_resolver.learn_from_web(
                            query,
                            enriched.constraints.model_dump(),
                            lookup_debug,
                        )
                        if learned is not None and lookup_debug is not None:
                            lookup_debug["competitor_kb_write"] = learned.debug_payload()
                except Exception as exc:
                    if lookup_debug is None:
                        lookup_debug = {}
                    lookup_debug["enrichment_interpret_error"] = f"{type(exc).__name__}: {exc}"
            elif lookup_debug is None:
                lookup_debug = {
                    "attempted": False,
                    "accepted": False,
                    "reason": "enrichment_returned_no_context",
                }
        elif self.competitor_lookup is not None:
            lookup_debug = {"attempted": False, "accepted": False, "reason": gate_reason}

        hard = hard_constraints(query, pre, enriched)
        hard, catalog_conflicts = apply_verified_catalog_constraints(hard, competitor_resolution)
        payload = interpretation.model_dump()
        payload["hard_constraints"] = hard
        if competitor_resolution is not None:
            payload["competitor_resolution"] = competitor_resolution.debug_payload()
        if source_decode is not None:
            payload["source_decode"] = source_decode.debug_payload()
        if enriched is not None:
            payload["pre_enrichment_interpretation"] = pre.model_dump()
        if lookup_debug is not None:
            payload["competitor_lookup"] = lookup_debug
            self._log_enrichment_diagnostic(query, lookup_debug)
        self._log_attribute_diagnostic(
            query,
            pre_interpretation=pre,
            interpretation=interpretation,
            hard=hard,
        )

        if catalog_conflicts:
            payload["catalog_conflicts"] = catalog_conflicts
            return MatchResult(
                query=query,
                status="NOT_FOUND",
                reason="QUERY_REJECTED: VERIFIED_CATALOG_CONFLICT: " + ", ".join(catalog_conflicts),
                query_interpretation=payload,
            )

        if not interpretation.searchable:
            return MatchResult(
                query=query,
                status="NOT_FOUND",
                reason=f"QUERY_REJECTED: {interpretation.reason}",
                query_interpretation=payload,
            )

        normalized = self._normalize(interpretation.normalized_query) or query
        resolved = bool(competitor_resolution is not None and competitor_resolution.resolved)
        if resolved and normalized != query:
            retrieval_query = normalized
            rendered = build_constraint_rendered_query(interpretation.constraints)
            canonical = self._normalize(rendered) if rendered else None
            canonical = canonical if canonical and canonical != retrieval_query else None
            strategy = "competitor_resolved_technical_plus_catalog"
        elif source_decode is not None and normalized != query:
            retrieval_query = normalized
            rendered = build_constraint_rendered_query(interpretation.constraints)
            canonical = self._normalize(rendered) if rendered else None
            canonical = canonical if canonical and canonical != retrieval_query else None
            strategy = "competitor_decoded_technical_plus_catalog"
        elif enriched is not None and normalized != query:
            retrieval_query = normalized
            rendered = build_constraint_rendered_query(enriched.constraints)
            canonical = self._normalize(rendered) if rendered else None
            canonical = canonical if canonical and canonical != retrieval_query else None
            strategy = "web_enriched_technical_plus_catalog"
        else:
            retrieval_query = query
            canonical = normalized if normalized != query else None
            strategy = "original_plus_canonical" if canonical else "original_only"

        payload["retrieval_trace"] = {
            "strategy": strategy,
            "source_query": query,
            "retrieval_query": retrieval_query,
            "alternate_query": canonical,
            "pre_enrichment_normalized_query": self._normalize(pre.normalized_query),
            "enriched_normalized_query": self._normalize(enriched.normalized_query) if enriched else None,
            "web_enrichment_applied": enriched is not None,
        }
        return PreparedQuery(
            interpretation=interpretation,
            pre_interpretation=pre,
            enriched_interpretation=enriched,
            source_decode=source_decode,
            competitor_resolution=competitor_resolution,
            hard_constraints=hard,
            interpretation_payload=payload,
            retrieval_query=retrieval_query,
            canonical_query=canonical,
            retrieval_strategy=strategy,
        )
