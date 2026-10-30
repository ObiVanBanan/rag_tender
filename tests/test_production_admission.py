"""Regression tests for safe API admission without third-party model calls."""
from __future__ import annotations

from threading import Event, Thread

import pytest
from fastapi.testclient import TestClient

from nomenclature_matcher.application.admission import (
    AdmissionRejected,
    RequestAdmission,
)
from nomenclature_matcher.api import create_app


def test_rolling_hour_budget_expires_and_counts_items() -> None:
    now = [0.0]
    admission = RequestAdmission(
        max_inflight_batches=1,
        max_items_per_hour=3,
        clock=lambda: now[0],
    )
    with admission.reserve(2):
        pass
    with admission.reserve(1):
        pass
    with pytest.raises(AdmissionRejected) as error:
        with admission.reserve(1):
            pass
    assert error.value.reason == "HOURLY_ITEM_LIMIT_REACHED"
    assert error.value.retry_after_seconds == 3600

    now[0] = 3601.0
    with admission.reserve(3):
        pass


def test_rejected_busy_batch_does_not_spend_hourly_budget() -> None:
    admission = RequestAdmission(max_inflight_batches=1, max_items_per_hour=2)
    entered = Event()
    release = Event()

    def hold_one_slot() -> None:
        with admission.reserve(1):
            entered.set()
            assert release.wait(timeout=5)

    thread = Thread(target=hold_one_slot)
    thread.start()
    try:
        assert entered.wait(timeout=5)
        with pytest.raises(AdmissionRejected) as error:
            with admission.reserve(1):
                pass
        assert error.value.reason == "MATCHER_BUSY"
    finally:
        release.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    with admission.reserve(1):
        pass
    with pytest.raises(AdmissionRejected):
        with admission.reserve(1):
            pass


def test_provider_exception_does_not_refund_attempt() -> None:
    admission = RequestAdmission(max_items_per_hour=1)
    with pytest.raises(RuntimeError):
        with admission.reserve(1):
            raise RuntimeError("provider may already have charged")
    with pytest.raises(AdmissionRejected):
        with admission.reserve(1):
            pass


def test_overlarge_batch_is_rejected_before_provider_calls() -> None:
    admission = RequestAdmission(max_items_per_hour=2)
    with pytest.raises(AdmissionRejected) as error:
        with admission.reserve(3):
            pass
    assert error.value.reason == "BATCH_EXCEEDS_HOURLY_LIMIT"
    with admission.reserve(2):
        pass


def test_api_shares_budget_between_match_and_shortlist() -> None:
    # Keep these fake adapters completely disconnected from model providers.
    class FakeMatcher:
        def match_one_hybrid_with_rerank(self, query):
            from nomenclature_matcher.models import MatchResult
            return MatchResult(query=query, status="NOT_FOUND")

    class FakeHistory:
        def __init__(self):
            self.records = []

        def record(self, **kwargs):
            self.records.append(kwargs)

    class FakeRuntime:
        def __init__(self):
            from types import SimpleNamespace
            self.settings = SimpleNamespace(
                api_max_batch_size=10,
                api_max_items_per_hour=2,
                api_max_inflight_batches=1,
                match_trace_enabled=False,
                app_env="development",
                api_auth_token="",
            )
            self.matcher = FakeMatcher()
            self.history = FakeHistory()

        def ready(self):
            return True

        def close(self):
            pass

    runtime = FakeRuntime()
    app = create_app(runtime_factory=lambda: runtime)
    with TestClient(app) as client:
        first = client.post(
            "/v1/match",
            headers={"X-Request-ID": "shared-id"},
            json={"products": ["first"]},
        )
        second = client.post(
            "/v1/shortlist",
            headers={"X-Request-ID": "shared-id"},
            json={"queries": [{"query": "second", "working_medium": "UNKNOWN"}]},
        )
        rejected = client.post(
            "/v1/match",
            headers={"X-Request-ID": "shared-id"},
            json={"products": ["third"]},
        )

    assert first.status_code == second.status_code == 200
    assert rejected.status_code == 429
    assert rejected.json()["detail"]["code"] == "HOURLY_ITEM_LIMIT_REACHED"
    assert int(rejected.headers["Retry-After"]) >= 1

    # Both completed snapshots are retained, notwithstanding the client ID.
    assert [r["request_id"] for r in runtime.history.records] == [
        "shared-id", "shared-id"
    ]
    assert runtime.history.records[0]["response_payload"]["results"][0]["input"] == "first"
    assert runtime.history.records[1]["response_payload"]["results"][0]["input"] == "second"


def test_shortlist_gas_only_blocks_explicit_liquid_and_never_auto_approves() -> None:
    from nomenclature_matcher.application.shortlist import build_analyst_shortlist
    from nomenclature_matcher.domain.medium import WorkingMedium
    from nomenclature_matcher.models import MatchResult, SearchCandidate

    def candidate(identifier: int, medium: str) -> SearchCandidate:
        return SearchCandidate(
            ld_id=identifier,
            name=f"LD {identifier}",
            article=f"A-{identifier}",
            score=0.2,
            properties=[{"name": "Рабочая среда", "values": [medium]}],
        )

    result = MatchResult(
        query="Кран для газа",
        status="MATCHED",
        candidates=[
            candidate(1, "Жидкость"),
            candidate(2, "Газ"),
            candidate(3, "Вода и газ"),
            candidate(4, "Неизвестно"),
        ],
    )
    answer = build_analyst_shortlist(result, WorkingMedium.GAS)
    assert [c["ld_id"] for c in answer["blocked_candidates"]] == [1]
    assert [c["ld_id"] for c in answer["candidates"]] == [2, 3, 4]
    assert answer["candidate_count"] == 3
    assert all(c["gas_certification"] == "UNVERIFIED" for c in answer["candidates"])
    assert all(c["automatic_approval"] is False for c in answer["candidates"])
    assert answer["candidates"][-1]["working_medium"]["disposition"] == "NEEDS_EVIDENCE"
