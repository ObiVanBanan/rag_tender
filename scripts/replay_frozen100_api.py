"""Replay the exact frozen100 benchmark through the running *demo API*.

No GOLD ids are ever sent to the API; all GOLD comparison remains local.
Run once against the original image/commit and once against the new image,
with the same CSV, Qdrant snapshot, model keys and model versions.
Reports include labels: save under .tmp/ and do not commit them.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import statistics
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from eval_competitor_analogs import load_embedded_cases


def grade_one(case: dict, match: dict) -> dict:
    acceptable = {int(x) for x in case["acceptable_ld_ids"]}
    status = match.get("status")
    first = (match.get("recommended") or [{}])[0]
    product_id = first.get("ld_id")
    try:
        picked = int(product_id) if product_id is not None else None
    except (ValueError, TypeError):
        picked = None
    if status == "MATCHED":
        verdict = "PASS" if picked in acceptable else "FAIL_WRONG_LD"
    elif status == "NOT_FOUND":
        verdict = "FAIL_NOT_FOUND"
    else:
        verdict = "FAIL_PIPELINE"
    return {
        "query": case["query"],
        "acceptable_ld_ids": sorted(acceptable),
        "actual_status": status,
        "returned_ld_id": picked,
        "verdict": verdict,
        "latency_ms": (match.get("metrics") or {}).get("latency_ms"),
    }


def run(cases: list[dict], *, url: str, authorization: str | None, timeout: float) -> list[dict]:
    rows = []
    for i, case in enumerate(cases, 1):
        started = time.perf_counter()
        headers = {"Content-Type": "application/json"}
        if authorization:
            headers["Authorization"] = authorization
        req = Request(url, method="POST", headers=headers,
                      data=json.dumps({"products": [case["query"]]}, ensure_ascii=False).encode("utf-8"))
        try:
            with urlopen(req, timeout=timeout) as response:
                result = json.load(response)["results"][0]
        except (HTTPError, URLError, KeyError, IndexError, OSError, ValueError, TimeoutError) as exc:
            if isinstance(exc, HTTPError) and exc.code in (401, 403):
                raise RuntimeError("API authorization failed; refusing misleading benchmark") from exc
            result = {"status": "ERROR", "recommended": [],
                      "metrics": {"latency_ms": round((time.perf_counter() - started)*1000,1)}}
        rows.append(grade_one(case, result))
        if i % 10 == 0:
            print(f"Replayed {i}/{len(cases)} requests")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default="http://127.0.0.1:8000/v1/demo/match")
    ap.add_argument("--sample", type=int, default=100)
    ap.add_argument("--seed", type=int, default=53)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--username", default=os.getenv("PUBLIC_DEMO_USERNAME", "demo"))
    ap.add_argument("--password-env", default="PUBLIC_DEMO_PASSWORD",
                    help="Environment variable containing Basic auth password (not a CLI password)")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    cases = load_embedded_cases()
    if args.sample != 100 or args.seed != 53:
        ap.error("Frozen promotion gate uses only --sample 100 --seed 53")
    cases = random.Random(args.seed).sample(cases, args.sample)
    password = os.getenv(args.password_env)
    if password and not args.url.startswith(("https://","http://127.0.0.1:","http://localhost:")):
        ap.error("Refusing to transmit Basic auth over plaintext remote HTTP")
    authorization = None
    if password:
        token = base64.b64encode(f"{args.username}:{password}".encode("utf-8")).decode("ascii")
        authorization = f"Basic {token}"

    rows = run(cases, url=args.url, authorization=authorization, timeout=args.timeout)
    passed = sum(row["verdict"] == "PASS" for row in rows)
    errors = sum(row["verdict"] == "FAIL_PIPELINE" for row in rows)
    timings = [float(row["latency_ms"]) for row in rows if isinstance(row.get("latency_ms"), (int, float))]
    payload = {
        "dataset_source": "embedded:competitor_analog_hit_any_min_v1",
        "sample":args.sample, "seed":args.seed,
        "summary": {
            "evaluated_queries": len(rows),
            "hit_any_rate": passed / len(rows),
            "pass": passed, "fail_pipeline":errors,
            "latency_p50_ms": round(statistics.median(timings),1) if timings else None,
        },
        "cases":rows,
    }
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Frozen100 PASS {passed}/{len(rows)}, API errors {errors}; written {args.out}")
    if errors:
        raise SystemExit("REJECT: API errors invalidate replay; check provider/service logs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
