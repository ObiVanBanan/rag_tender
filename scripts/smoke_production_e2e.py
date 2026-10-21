#!/usr/bin/env python3
"""Real production smoke against a running RAG Tender stack.

Unlike TestClient unit tests this makes two real HTTP matching calls. It does
not assert a particular LD article (which depends on live index/models).
Set RAG_TENDER_SMOKE_READ_DSN to an administrator/read-only DB connection URL
for --verify-history; the API's INSERT-only role is deliberately insufficient.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


def http_json(
    base_url: str,
    path: str,
    *,
    token: str | None = None,
    request_id: str | None = None,
    body: dict | None = None,
    timeout: int = 120,
) -> tuple[dict, str | None]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if request_id:
        headers["X-Request-ID"] = request_id
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = Request(
        base_url.rstrip("/") + path,
        headers=headers,
        data=data,
        method="POST" if body is not None else "GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")), response.headers.get("X-Request-ID")
    except HTTPError as exc:
        # Never print Authorization headers, database credentials, raw candidates.
        raise RuntimeError(f"{path}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"{path}: connection failed: {type(exc.reason).__name__}") from exc


def verify_shortlist(data: dict, request_id: str) -> tuple[int, int]:
    if data.get("request_id") != request_id:
        raise AssertionError("Shortlist did not preserve X-Request-ID correlation")
    results = data.get("results")
    if not isinstance(results, list) or len(results) != 1:
        raise AssertionError("Expected one shortlist result")
    result = results[0]
    if result.get("status") == "ERROR":
        raise AssertionError("Shortlist provider or retrieval failed")
    if result.get("automatic_approval") is not False or result.get("human_review_required") is not True:
        raise AssertionError("Shortlist attempted to auto-approve an industrial substitute")
    if result.get("requested_medium") != "GAS":
        raise AssertionError("Gas request lost its phase classification")
    suggested = result.get("candidates") or []
    blocked = result.get("blocked_candidates") or []
    for candidate in suggested:
        medium = candidate.get("working_medium") or {}
        if medium.get("disposition") == "BLOCKED_CONFLICT":
            raise AssertionError("Liquid-only candidate leaked into GAS suggestions")
        if candidate.get("gas_certification") != "UNVERIFIED":
            raise AssertionError("Gas certification claimed without verified evidence")
        if candidate.get("automatic_approval") is not False:
            raise AssertionError("Candidate auto-approved without human check")
    for candidate in blocked:
        medium = candidate.get("working_medium") or {}
        if medium.get("disposition") != "BLOCKED_CONFLICT":
            raise AssertionError("Blocked candidate lacks explicit gas/liquid conflict")
    if not suggested and not blocked:
        raise AssertionError("No retrieval candidates returned; full retrieval smoke not demonstrated")
    return len(suggested), len(blocked)


def verify_database_snapshots(request_id: str) -> None:
    dsn = os.environ.get("RAG_TENDER_SMOKE_READ_DSN")
    if not dsn:
        raise RuntimeError("--verify-history requires RAG_TENDER_SMOKE_READ_DSN")
    import psycopg

    with psycopg.connect(dsn, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT history_id, request_json, response_json
                FROM rag_match_requests
                WHERE request_id = %s
                ORDER BY created_at, history_id
                """,
                (request_id,),
            )
            rows = cursor.fetchall()
    if len(rows) != 2 or len({str(row[0]) for row in rows}) != 2:
        raise AssertionError("Exactly two independent snapshots with one X-Request-ID are required")
    request_kinds = {
        "match" if "products" in row[1] else
        "shortlist" if "queries" in row[1] else "unknown"
        for row in rows
    }
    if request_kinds != {"match", "shortlist"}:
        raise AssertionError("Request snapshot types were not retained")
    if not all(isinstance(row[2].get("results"), list) for row in rows):
        raise AssertionError("Response snapshots are missing or malformed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--verify-history", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("API_AUTH_TOKEN")
    if not token:
        parser.error("Set API_AUTH_TOKEN in the environment; do not pass secrets on the command line")

    request_id = "rag-e2e-" + uuid4().hex
    live, _ = http_json(args.base_url, "/health/live", timeout=args.timeout)
    ready, _ = http_json(args.base_url, "/health/ready", timeout=args.timeout)
    if live.get("status") != "ok" or ready.get("status") != "ok":
        raise AssertionError("Health and dependency readiness checks must both pass")

    gas, response_id = http_json(
        args.base_url,
        "/v1/shortlist",
        token=token,
        request_id=request_id,
        body={"queries": [{
            "query": "Кран шаровой газовый фланцевый DN50 PN16",
            "working_medium": "GAS",
        }], "max_candidates": 20},
        timeout=args.timeout,
    )
    if response_id != request_id:
        raise AssertionError("Shortlist response correlation header was not preserved")
    n_suggested, n_blocked = verify_shortlist(gas, request_id)

    match, response_id = http_json(
        args.base_url,
        "/v1/match",
        token=token,
        request_id=request_id,
        body={"products": ["Кран шаровой фланцевый для воды DN50 PN16"]},
        timeout=args.timeout,
    )
    if response_id != request_id or match.get("request_id") != request_id:
        raise AssertionError("Match correlation ID was not preserved")
    if len(match.get("results", [])) != 1 or match["results"][0].get("status") == "ERROR":
        raise AssertionError("Match API returned provider ERROR or invalid response")

    if args.verify_history:
        verify_database_snapshots(request_id)

    print(
        f"PASS E2E: ready; shortlist suggestions={n_suggested} blocked={n_blocked}; "
        f"match={match['results'][0]['status']}; "
        f"history_verified={args.verify_history}; request_id={request_id}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AssertionError, RuntimeError) as exc:
        print(f"FAIL E2E: {exc}", file=sys.stderr)
        sys.exit(1)
