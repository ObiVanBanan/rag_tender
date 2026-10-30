from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from time import perf_counter
from typing import Annotated, Any, Callable, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from .observability import (
    PROMETHEUS_CONTENT_TYPE,
    dec_in_flight,
    get_request_id,
    inc_in_flight,
    log_http_request_completed,
    log_match_trace,
    log_operational_event,
    record_api_error,
    record_batch_size,
    record_http_request,
    render_metrics,
    reset_request_id,
    resolve_request_id,
    set_request_id,
)
from .domain.medium import CatalogMedium, WorkingMedium, classify_medium_text
from .public_auth import valid_basic_auth
from .application.admission import AdmissionRejected, RequestAdmission
from .application.matching import match_products
from .application.request_history import RequestHistoryRecorder, RequestHistoryRecord
from .application.shortlist import shortlist_product
from .application.telemetry import NullTelemetry
from .domain.query_signals import explicit_working_medium_from_query
from .production import (
    ProductionRuntime,
    build_production_runtime,
)

logger = logging.getLogger(__name__)


MatchQuery = Annotated[str, StringConstraints(min_length=1, max_length=4000)]


class MatchRequest(BaseModel):
    products: list[MatchQuery] = Field(min_length=1)

    @field_validator("products")
    @classmethod
    def validate_products(cls, value: list[str]) -> list[str]:
        for index, product in enumerate(value):
            if not isinstance(product, str) or not product.strip():
                raise ValueError(f"products[{index}] must be a non-empty string")
        return value


class ProductMatch(BaseModel):
    input: str
    status: Literal["MATCHED", "NOT_FOUND", "ERROR"]
    matched_name: str | None = None
    matched_article: str | None = None
    score: float | None = None
    confidence: float | None = None
    error_code: str | None = None


class MatchResponse(BaseModel):
    request_id: str
    results: list[ProductMatch]
    latency_ms: float


class AnalystQuery(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    working_medium: WorkingMedium

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must be a non-empty string")
        return value

    @model_validator(mode="after")
    def validate_medium_consistency(self) -> AnalystQuery:
        explicit = explicit_working_medium_from_query(self.query)
        if explicit is None:
            return self
        parsed = classify_medium_text([explicit])
        if parsed is CatalogMedium.UNKNOWN:
            return self
        if self.working_medium is WorkingMedium.UNKNOWN:
            raise ValueError("working_medium must reflect the medium stated in query")
        if parsed.value != self.working_medium.value:
            raise ValueError("working_medium conflicts with the medium stated in query")
        return self


class ShortlistRequest(BaseModel):
    queries: list[AnalystQuery] = Field(min_length=1)
    max_candidates: int = Field(default=20, ge=1, le=20)


class ShortlistMediumDetails(BaseModel):
    requested: WorkingMedium
    catalog_classification: Literal["GAS", "LIQUID", "BOTH", "UNKNOWN"]
    disposition: Literal[
        "MEDIUM_MATCH_REVIEW_REQUIRED",
        "NEEDS_EVIDENCE",
        "BLOCKED_CONFLICT",
    ]


class ShortlistCandidate(BaseModel):
    rank: int
    ld_id: int
    article: str | None
    name: str
    url: str | None
    retrieval_score: float | None
    dense_score: float | None
    dense_rank: int | None
    bm25_score: float | None
    bm25_rank: int | None
    rrf_score: float | None
    retrieval_sources: list[str]
    attributes: dict[str, Any]
    properties: list[dict[str, Any]]
    reranker: dict[str, Any]
    working_medium: ShortlistMediumDetails
    gas_certification: Literal["UNVERIFIED"]
    human_review_required: Literal[True]
    automatic_approval: Literal[False]


class ShortlistResult(BaseModel):
    input: str
    status: Literal["REVIEW_REQUIRED", "NO_CANDIDATES", "ERROR"]
    error_code: str | None
    requested_medium: WorkingMedium
    decision: Literal["REVIEW_REQUIRED"]
    human_review_required: Literal[True]
    automatic_approval: Literal[False]
    candidates: list[ShortlistCandidate]
    blocked_candidates: list[ShortlistCandidate]
    candidate_count: int
    blocked_candidate_count: int
    candidate_pool_truncated: bool
    pool_size: int


class ShortlistResponse(BaseModel):
    request_id: str
    results: list[ShortlistResult]
    latency_ms: float


RuntimeFactory = Callable[[], ProductionRuntime]


def create_app(runtime_factory: RuntimeFactory | None = None) -> FastAPI:
    runtime_factory = runtime_factory or build_production_runtime

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = runtime_factory()
        app.state.runtime = runtime
        telemetry = getattr(runtime.matcher, "telemetry", None) or NullTelemetry()
        app.state.history_recorder = RequestHistoryRecorder(runtime.history, telemetry)
        app.state.request_admission = RequestAdmission(
            max_inflight_batches=getattr(
                runtime.settings, "api_max_inflight_batches", 1
            ),
            max_items_per_hour=getattr(
                runtime.settings, "api_max_items_per_hour", 500
            ),
        )
        try:
            yield
        finally:
            runtime.close()

    app = FastAPI(
        title="RAG Tender Matcher API",
        version="1.0.0",
        description=(
            "Production API around the validated rag-tender champion pipeline. "
            "Each product is matched independently."
        ),
        lifespan=lifespan,
    )

    def openapi_with_bearer_auth():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        schemes = schema.setdefault("components", {}).setdefault("securitySchemes", {})
        schemes["BearerAuth"] = {"type": "http", "scheme": "bearer"}
        schemes["DemoBasicAuth"] = {"type": "http", "scheme": "basic"}
        for path, path_item in schema.get("paths", {}).items():
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                operation["security"] = (
                    [] if path in {"/health/live", "/health/ready"}
                    else [{"DemoBasicAuth": []}] if path.startswith("/v1/demo/")
                    else [{"BearerAuth": []}]
                )
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi_with_bearer_auth

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = resolve_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        token = set_request_id(request_id)
        inc_in_flight()
        started = perf_counter()
        status_code = 500
        response = None
        try:
            if not _is_authorized(request):
                response = JSONResponse(
                    status_code=401,
                    content={"detail": "unauthorized"},
                    headers={"WWW-Authenticate": (
                        'Basic realm="RAG Tender Admin"' if request.url.path in {"/demo/stats", "/v1/demo/stats"}
                        else 'Basic realm="RAG Tender Demo"' if request.url.path == "/demo" or request.url.path.startswith("/v1/demo/")
                        else "Bearer"
                    )},
                )
                status_code = response.status_code
                return response
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = perf_counter() - started
            if response is not None:
                response.headers["X-Request-ID"] = request_id
            dec_in_flight()
            record_http_request(
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_seconds=duration,
            )
            log_http_request_completed(
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration * 1000,
            )
            reset_request_id(token)

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def health_ready(request: Request):
        runtime: ProductionRuntime = request.app.state.runtime
        if not runtime.ready():
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(content=render_metrics(), media_type=PROMETHEUS_CONTENT_TYPE)

    @app.post("/v1/match", response_model=MatchResponse)
    def match(payload: MatchRequest, request: Request):
        runtime: ProductionRuntime = request.app.state.runtime
        if len(payload.products) > runtime.settings.api_max_batch_size:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Batch is too large. "
                    f"Maximum size is {runtime.settings.api_max_batch_size}."
                ),
            )

        request_id = get_request_id() or resolve_request_id(None)
        created_at = datetime.now(timezone.utc)
        started = perf_counter()
        request_payload = payload.model_dump(mode="json")
        trace_enabled = bool(getattr(runtime.settings, "match_trace_enabled", True))
        record_batch_size(len(payload.products))
        log_match_trace(
            "request_started",
            enabled=trace_enabled,
            batch_size=len(payload.products),
        )

        try:
            # Admission is shared between /v1/match and /v1/shortlist.
            # Only the expensive matcher run occupies an inflight slot.
            with request.app.state.request_admission.reserve(len(payload.products)):
                raw_results = match_products(runtime.matcher, payload.products)
            latency_ms = round((perf_counter() - started) * 1000, 3)
            response = MatchResponse(
                request_id=request_id,
                results=[ProductMatch.model_validate(item) for item in raw_results],
                latency_ms=latency_ms,
            )
            response_payload = response.model_dump(mode="json")
            completed_at = datetime.now(timezone.utc)
            matched_count = sum(
                item.status == "MATCHED" for item in response.results
            )
            history_status = (
                "PARTIAL_ERROR"
                if any(item.status == "ERROR" for item in response.results)
                else "OK"
            )
            _history_recorder(request).record(
                RequestHistoryRecord(
                    request_id=request_id,
                    created_at=created_at,
                    completed_at=completed_at,
                    status=history_status,
                    http_status=200,
                    product_count=len(payload.products),
                    matched_count=matched_count,
                    latency_ms=latency_ms,
                    request_payload=request_payload,
                    response_payload=response_payload,
                ),
                trace_enabled=trace_enabled,
            )
            not_found_count = sum(
                item.status == "NOT_FOUND" for item in response.results
            )
            error_count = sum(item.status == "ERROR" for item in response.results)
            log_match_trace(
                "request_completed",
                enabled=trace_enabled,
                duration_ms=latency_ms,
                batch_size=len(payload.products),
                matched_count=matched_count,
                not_found_count=not_found_count,
                error_count=error_count,
            )
            severity = "ERROR" if error_count else ("WARNING" if not_found_count else "INFO")
            log_operational_event(
                "request_diagnostic",
                (
                    f"REQUEST {history_status}: {matched_count} matched, "
                    f"{not_found_count} not found, {error_count} errors "
                    f"of {len(payload.products)} items ({latency_ms:.0f} ms)"
                ),
                severity=severity,
                batch_size=len(payload.products),
                matched_count=matched_count,
                not_found_count=not_found_count,
                error_count=error_count,
                duration_ms=latency_ms,
                slow_request=latency_ms >= 10000,
            )
            return response
        except AdmissionRejected as exc:
            record_api_error(exc.reason)
            raise HTTPException(
                status_code=429,
                detail={"code": exc.reason, "message": "Matcher capacity exhausted"},
                headers={"Retry-After": str(exc.retry_after_seconds)},
            ) from exc
        except Exception as exc:
            latency_ms = round((perf_counter() - started) * 1000, 3)
            completed_at = datetime.now(timezone.utc)
            logger.exception("Unhandled production API error")
            record_api_error("INTERNAL_ERROR")
            response_payload = {
                "request_id": request_id,
                "error": "internal_error",
            }
            _history_recorder(request).record(
                RequestHistoryRecord(
                    request_id=request_id,
                    created_at=created_at,
                    completed_at=completed_at,
                    status="ERROR",
                    http_status=500,
                    product_count=len(payload.products),
                    matched_count=0,
                    latency_ms=latency_ms,
                    request_payload=request_payload,
                    response_payload=response_payload,
                    error=f"{type(exc).__name__}: {exc}",
                ),
                trace_enabled=trace_enabled,
            )
            log_match_trace(
                "request_failed",
                enabled=trace_enabled,
                duration_ms=latency_ms,
                error_type=type(exc).__name__,
            )
            log_operational_event(
                "request_diagnostic",
                f"REQUEST ERROR — {type(exc).__name__} ({latency_ms:.0f} ms)",
                severity="ERROR",
                batch_size=len(payload.products),
                matched_count=0,
                not_found_count=0,
                error_count=len(payload.products),
                duration_ms=latency_ms,
                error_type=type(exc).__name__,
                slow_request=latency_ms >= 10000,
            )
            return JSONResponse(status_code=500, content=response_payload)

    @app.post("/v1/shortlist", response_model=ShortlistResponse)
    def shortlist(payload: ShortlistRequest, request: Request):
        runtime: ProductionRuntime = request.app.state.runtime
        if len(payload.queries) > runtime.settings.api_max_batch_size:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Batch is too large. "
                    f"Maximum size is {runtime.settings.api_max_batch_size}."
                ),
            )

        request_id = get_request_id() or resolve_request_id(None)
        created_at = datetime.now(timezone.utc)
        started = perf_counter()
        request_payload = payload.model_dump(mode="json")
        trace_enabled = bool(getattr(runtime.settings, "match_trace_enabled", True))
        record_batch_size(len(payload.queries))
        log_match_trace(
            "shortlist_request_started",
            enabled=trace_enabled,
            batch_size=len(payload.queries),
            max_candidates=payload.max_candidates,
        )

        try:
            with request.app.state.request_admission.reserve(len(payload.queries)):
                results = [
                    shortlist_product(
                        runtime.matcher,
                        item.query,
                        item.working_medium,
                        max_candidates=payload.max_candidates,
                    )
                    for item in payload.queries
                ]
        except AdmissionRejected as exc:
            record_api_error(exc.reason)
            raise HTTPException(
                status_code=429,
                detail={"code": exc.reason, "message": "Matcher capacity exhausted"},
                headers={"Retry-After": str(exc.retry_after_seconds)},
            ) from exc
        latency_ms = round((perf_counter() - started) * 1000, 3)
        response = ShortlistResponse(
            request_id=request_id,
            results=results,
            latency_ms=latency_ms,
        )
        response_payload = response.model_dump(mode="json")
        completed_at = datetime.now(timezone.utc)
        errors = sum(item["status"] == "ERROR" for item in results)
        _history_recorder(request).record(
            RequestHistoryRecord(
                request_id=request_id,
                created_at=created_at,
                completed_at=completed_at,
                status="PARTIAL_ERROR" if errors else "OK",
                http_status=200,
                product_count=len(results),
                matched_count=sum(item["candidate_count"] > 0 for item in results),
                latency_ms=latency_ms,
                request_payload=request_payload,
                response_payload=response_payload,
            ),
            trace_enabled=trace_enabled,
        )
        log_match_trace(
            "shortlist_request_completed",
            enabled=trace_enabled,
            duration_ms=latency_ms,
            batch_size=len(results),
            error_count=errors,
            suggestion_count=sum(item["candidate_count"] for item in results),
        )
        return response

    from .business_demo import router as business_demo_router
    app.include_router(business_demo_router)
    return app


def _is_authorized(request: Request) -> bool:
    """Require bearer auth outside development; health probes stay public."""
    if request.url.path in {
        "/health/live",
        "/health/ready",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/docs/oauth2-redirect",
    }:
        return True
    runtime = getattr(request.app.state, "runtime", None)
    settings = getattr(runtime, "settings", None)
    path = request.url.path
    is_demo = path == "/demo" or path.startswith("/v1/demo/") or path.startswith("/demo/")
    if is_demo:
        is_stats = path in {"/demo/stats", "/v1/demo/stats"}
        user = str(getattr(settings, "public_demo_username", "demo") or "demo")
        password = str(getattr(settings, "public_demo_password", "") or "")
        admin = str(getattr(settings, "public_demo_admin_username", "ld-admin") or "ld-admin")
        admin_password = str(getattr(settings, "public_demo_admin_password", "") or "")
        header = request.headers.get("Authorization")
        is_admin = bool(admin_password) and valid_basic_auth(header, username=admin, password=admin_password)
        if is_stats:
            return is_admin
        if password:
            return is_admin or valid_basic_auth(header, username=user, password=password)
        return str(getattr(settings, "app_env", "development")).lower() not in {"production", "prod"}
    configured = getattr(settings, "api_auth_token", "")
    token = (
        configured.get_secret_value()
        if callable(getattr(configured, "get_secret_value", None))
        else str(configured or "")
    )
    environment = str(getattr(settings, "app_env", "development")).lower()
    if not token:
        return environment not in {"production", "prod"}
    scheme, separator, supplied = request.headers.get("Authorization", "").partition(" ")
    return bool(
        separator
        and scheme.lower() == "bearer"
        and hmac.compare_digest(
            supplied.strip().encode("utf-8"),
            token.encode("utf-8"),
        )
    )


def _history_recorder(request: Request) -> RequestHistoryRecorder:
    return request.app.state.history_recorder


app = create_app()
