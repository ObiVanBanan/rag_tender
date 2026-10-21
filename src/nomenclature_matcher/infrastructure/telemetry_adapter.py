from __future__ import annotations

from typing import Any

from .. import observability


class ObservabilityTelemetry:
    """Application telemetry port backed by the existing metrics and JSON logs."""

    def log_match_trace(self, stage: str, *, enabled: bool = True, **payload: Any) -> None:
        observability.log_match_trace(stage, enabled=enabled, **payload)

    def log_operational_event(
        self, event: str, summary: str, *, severity: str = "INFO", **payload: Any
    ) -> None:
        observability.log_operational_event(
            event, summary, severity=severity, **payload
        )

    def record_match_item(self, status: str, duration_seconds: float) -> None:
        observability.record_match_item(status, duration_seconds)

    def record_match_decision(self, status: str, reason: str | None) -> str:
        return observability.record_match_decision(status, reason)

    def record_web_enrichment(self, status: str, duration_seconds: float) -> None:
        observability.record_web_enrichment(status, duration_seconds)

    def record_enrichment_gate(self, reason: str) -> None:
        observability.record_enrichment_gate(reason)

    def record_attribute_conflicts(self, fields: list[str]) -> None:
        observability.record_attribute_conflicts(fields)

    def record_history_write(self, status: str, duration_seconds: float) -> None:
        observability.record_history_write(status, duration_seconds)

    def record_api_error(self, error_type: str) -> None:
        observability.record_api_error(error_type)

    def set_item_index(self, item_index: int | None) -> Any:
        return observability.set_item_index(item_index)

    def reset_item_index(self, token: Any) -> None:
        observability.reset_item_index(token)
