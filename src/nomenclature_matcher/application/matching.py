from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from .diagnostics import build_attribute_diagnostic, trim_text
from .ports import MatcherPort
from .telemetry import NullTelemetry

logger = logging.getLogger(__name__)


def match_products(matcher: MatcherPort, products: list[str]) -> list[dict[str, Any]]:
    """Application use case for the legacy one-result batch API."""
    results: list[dict[str, Any]] = []
    trace_enabled = bool(getattr(getattr(matcher, "settings", None), "match_trace_enabled", True))
    telemetry = getattr(matcher, "telemetry", None) or NullTelemetry()

    for index, product in enumerate(products, 1):
        token = telemetry.set_item_index(index)
        started = perf_counter()
        telemetry.log_match_trace("item_started", enabled=trace_enabled)
        try:
            match = None
            exception_reason = None
            try:
                match = matcher.match_one_hybrid_with_rerank(product)
            except Exception as exc:
                logger.exception("Product matching failed for one batch item")
                exception_reason = f"{type(exc).__name__}: {exc}"
                item = {
                    "input": product,
                    "status": "ERROR",
                    "matched_name": None,
                    "matched_article": None,
                    "score": None,
                    "confidence": None,
                    "error_code": type(exc).__name__,
                }
            else:
                if match.status == "MATCHED" and match.ld_product is not None:
                    confidence = match.selected[0].llm_confidence if match.selected else None
                    item = {
                        "input": product,
                        "status": "MATCHED",
                        "matched_name": match.ld_product.name,
                        "matched_article": match.ld_product.article,
                        "score": match.score,
                        "confidence": confidence,
                        "error_code": None,
                    }
                elif match.status == "RERANK_FAILED":
                    item = {
                        "input": product,
                        "status": "ERROR",
                        "matched_name": None,
                        "matched_article": None,
                        "score": None,
                        "confidence": None,
                        "error_code": "RERANK_FAILED",
                    }
                else:
                    item = {
                        "input": product,
                        "status": "NOT_FOUND",
                        "matched_name": None,
                        "matched_article": None,
                        "score": None,
                        "confidence": None,
                        "error_code": None,
                    }

            duration = perf_counter() - started
            results.append(item)
            telemetry.record_match_item(item["status"], duration)

            reason = getattr(match, "reason", None) if match is not None else exception_reason
            reason_code = telemetry.record_match_decision(item["status"], reason)
            interpretation = (
                getattr(match, "query_interpretation", None) or {}
                if match is not None
                else {}
            )
            lookup = interpretation.get("competitor_lookup") or {}
            after = interpretation.get("constraints") or {}
            before = (
                (interpretation.get("pre_enrichment_interpretation") or {}).get("constraints")
                or after
            )
            hard = interpretation.get("hard_constraints") or {}
            attribute_diagnostic = build_attribute_diagnostic(before, after, hard)
            conflict_fields = attribute_diagnostic["hard_conflict_fields"]

            if item["status"] == "MATCHED":
                summary = (
                    f"MATCHED → {item['matched_article'] or item['matched_name'] or 'unknown'} "
                    f"(confidence={item['confidence']}, {duration * 1000:.0f} ms)"
                )
                severity = "INFO"
            elif item["status"] == "NOT_FOUND":
                summary = f"NOT_FOUND — {reason_code} ({duration * 1000:.0f} ms)"
                severity = "WARNING"
            else:
                summary = f"ERROR — {item['error_code'] or reason_code} ({duration * 1000:.0f} ms)"
                severity = "ERROR"
            if conflict_fields:
                summary += " | HARD CONFLICT: " + ", ".join(conflict_fields)
                severity = "WARNING" if severity == "INFO" else severity

            telemetry.log_operational_event(
                "item_diagnostic",
                summary,
                severity=severity,
                input_query=trim_text(product, 500),
                status=item["status"],
                reason_code=reason_code,
                reason=trim_text(reason, 600),
                duration_ms=round(duration * 1000, 3),
                matched_name=item["matched_name"],
                matched_article=item["matched_article"],
                score=item["score"],
                confidence=item["confidence"],
                error_code=item["error_code"],
                candidate_count=len(getattr(match, "candidates", []) or []) if match is not None else 0,
                web_attempted=lookup.get("attempted"),
                web_accepted=lookup.get("accepted"),
                web_reason=trim_text(lookup.get("reason"), 220),
                web_duration_ms=lookup.get("duration_ms"),
                hard_conflict_fields=conflict_fields,
            )
            telemetry.log_match_trace(
                "item_completed",
                enabled=trace_enabled,
                status=item["status"],
                duration_ms=round(duration * 1000, 3),
                error_type=item["error_code"],
            )
        finally:
            telemetry.reset_item_index(token)

    return results
