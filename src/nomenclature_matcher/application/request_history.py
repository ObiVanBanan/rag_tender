from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Any

from .ports import RequestHistoryPort, TelemetryPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RequestHistoryRecord:
    request_id: str
    created_at: datetime
    completed_at: datetime
    status: str
    http_status: int
    product_count: int
    matched_count: int
    latency_ms: float
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    error: str | None = None


class RequestHistoryRecorder:
    """Persist a completed request audit without changing the API outcome."""

    def __init__(self, history: RequestHistoryPort, telemetry: TelemetryPort) -> None:
        self.history = history
        self.telemetry = telemetry

    def record(self, record: RequestHistoryRecord, *, trace_enabled: bool = True) -> None:
        started = perf_counter()
        self._emit("log_match_trace", "persist_started", enabled=trace_enabled)
        try:
            self.history.record(
                request_id=record.request_id,
                created_at=record.created_at,
                completed_at=record.completed_at,
                status=record.status,
                http_status=record.http_status,
                product_count=record.product_count,
                matched_count=record.matched_count,
                latency_ms=record.latency_ms,
                request_payload=record.request_payload,
                response_payload=record.response_payload,
                error=record.error,
            )
        except Exception as exc:
            duration = perf_counter() - started
            self._emit("record_history_write", "ERROR", duration)
            self._emit("record_api_error", "HISTORY_WRITE_FAILED")
            self._emit(
                "log_match_trace",
                "persist_failed",
                enabled=trace_enabled,
                duration_ms=round(duration * 1000, 3),
                error_type=type(exc).__name__,
            )
            logger.exception("Failed to persist request/response history")
            return

        duration = perf_counter() - started
        self._emit("record_history_write", "OK", duration)
        self._emit(
            "log_match_trace",
            "persist_completed",
            enabled=trace_enabled,
            duration_ms=round(duration * 1000, 3),
        )

    def _emit(self, method: str, *args: Any, **kwargs: Any) -> None:
        try:
            getattr(self.telemetry, method)(*args, **kwargs)
        except Exception as exc:
            logger.warning("Request history telemetry failed: %s", type(exc).__name__)
