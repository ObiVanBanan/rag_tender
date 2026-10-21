from __future__ import annotations

from typing import Any

from .diagnostics import classify_match_reason


class NullTelemetry:
    """No-op telemetry for tests and non-production matcher compositions."""

    def log_match_trace(self, stage: str, *, enabled: bool = True, **payload: Any) -> None:
        return None

    def log_operational_event(
        self, event: str, summary: str, *, severity: str = "INFO", **payload: Any
    ) -> None:
        return None

    def record_match_item(self, status: str, duration_seconds: float) -> None:
        return None

    @staticmethod
    def record_match_decision(status: str, reason: str | None) -> str:
        return classify_match_reason(status, reason)

    def record_web_enrichment(self, status: str, duration_seconds: float) -> None:
        return None

    def record_enrichment_gate(self, reason: str) -> None:
        return None

    def record_attribute_conflicts(self, fields: list[str]) -> None:
        return None

    def record_history_write(self, status: str, duration_seconds: float) -> None:
        return None

    def record_api_error(self, error_type: str) -> None:
        return None

    def set_item_index(self, item_index: int | None) -> None:
        return None

    def reset_item_index(self, token: Any) -> None:
        return None
