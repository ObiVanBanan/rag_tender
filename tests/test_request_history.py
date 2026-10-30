from __future__ import annotations

from datetime import datetime, timezone

from nomenclature_matcher.application.request_history import (
    RequestHistoryRecord,
    RequestHistoryRecorder,
)


class FakeHistory:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.records: list[dict[str, object]] = []

    def record(self, **values: object) -> None:
        if self.error:
            raise self.error
        self.records.append(values)


class FakeTelemetry:
    def __init__(self) -> None:
        self.events: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def __getattr__(self, name: str):
        def record(*args: object, **kwargs: object) -> None:
            self.events.append((name, args, kwargs))

        return record


class FailingTelemetry:
    def __getattr__(self, name: str):
        def record(*args: object, **kwargs: object) -> None:
            raise RuntimeError(f"telemetry unavailable: {name}")

        return record


def make_record() -> RequestHistoryRecord:
    now = datetime.now(timezone.utc)
    return RequestHistoryRecord(
        request_id="request-1",
        created_at=now,
        completed_at=now,
        status="OK",
        http_status=200,
        product_count=1,
        matched_count=1,
        latency_ms=12.5,
        request_payload={"products": ["valve"]},
        response_payload={"results": []},
    )


def test_request_history_recorder_persists_record_and_reports_success() -> None:
    history = FakeHistory()
    telemetry = FakeTelemetry()

    RequestHistoryRecorder(history, telemetry).record(make_record())

    assert len(history.records) == 1
    assert history.records[0]["request_id"] == "request-1"
    assert any(
        name == "record_history_write" and args[0] == "OK"
        for name, args, _ in telemetry.events
    )


def test_request_history_failure_is_reported_without_escaping() -> None:
    history = FakeHistory(RuntimeError("database unavailable"))
    telemetry = FakeTelemetry()

    RequestHistoryRecorder(history, telemetry).record(make_record(), trace_enabled=False)

    assert any(
        name == "record_history_write" and args[0] == "ERROR"
        for name, args, _ in telemetry.events
    )
    assert ("record_api_error", ("HISTORY_WRITE_FAILED",), {}) in telemetry.events
    assert ("log_match_trace", ("persist_started",), {"enabled": False}) in telemetry.events


def test_request_history_telemetry_failure_does_not_change_persistence_outcome() -> None:
    history = FakeHistory()

    RequestHistoryRecorder(history, FailingTelemetry()).record(make_record())

    assert len(history.records) == 1
    assert history.records[0]["request_id"] == "request-1"
