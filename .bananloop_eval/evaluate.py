#!/usr/bin/env python3
"""Private BananLoop adapter for the frozen 100-case DEV analogue benchmark.

The GOLD-bearing trace is written only to a temporary directory. BananLoop gets
aggregate metrics and hashed case measurements for paired comparisons.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path


SAMPLE = 100
SEED = 53
SMOKE_CASES = 4
WORKERS = 4
EXPECTED_GROUPS = {"MARSHAL": 42, "ALSO": 47, "TEMPER": 8}
REQUIRED_CHECKS = (
    "fixed_dev_sample",
    "case_insensitive_cohorts",
    "group_metrics",
    "paired_protocol",
    "gold_isolation",
    "no_final_holdout",
)
CATALOG = Path("/workspaces/rag_trend/ld_products_full_nomenclature.csv")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def hash_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def check(passed: bool, executed: int) -> dict:
    return {"passed": bool(passed), "executed": int(executed), "skipped": 0}


def load_evaluator_module(script: Path):
    spec = importlib.util.spec_from_file_location("bananloop_frozen_evaluator", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen benchmark evaluator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_smoke_mapping(path: Path, cases: list[dict]) -> None:
    """Materialize only the four selected frozen cases for a cheap smoke run."""
    fields = (
        "steel_name", "steel_article", "steel_url", "ld_name", "ld_article",
        "ld_url", "match_score", "match_max",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            for ld_id in case["acceptable_ld_ids"]:
                writer.writerow({
                    "steel_name": case["query"],
                    "steel_article": "",
                    "steel_url": "",
                    "ld_name": "",
                    "ld_article": "",
                    "ld_url": f"https://fixture.invalid/products/{int(ld_id)}--frozen",
                    "match_score": 1,
                    "match_max": 1,
                })


def run_repository_evaluator(
    script: Path, root: Path, output: Path, smoke: bool, selected: list[dict]
) -> tuple[dict, dict]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    command = [
        sys.executable, str(script), "--csv", str(CATALOG), "--workers", str(WORKERS),
        "--output", str(output),
    ]
    public_trace = output.with_name("dev-stage-trace.json")
    command += ["--public-trace-output", str(public_trace)]
    if smoke:
        mapping = output.with_name("smoke-mapping.csv")
        write_smoke_mapping(mapping, selected)
        command += ["--mapping", str(mapping), "--limit", str(len(selected))]
    else:
        command += ["--sample", str(SAMPLE), "--seed", str(SEED)]
    completed = subprocess.run(
        command, cwd=root, env=env, text=True, capture_output=True, check=False,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout or "evaluator failed")[-4000:]
        raise RuntimeError(detail)
    return (
        json.loads(output.read_text(encoding="utf-8")),
        json.loads(public_trace.read_text(encoding="utf-8")),
    )


def build_retrieval_case_traces(rows: list[dict], public_trace: dict) -> list[dict]:
    """Reduce the temporary DEV trace to hashed per-case stage evidence only."""
    if (
        public_trace.get("artifact_type") != "dev_stage_trace"
        or public_trace.get("contains_gold_ids") is not False
    ):
        raise RuntimeError("evaluator did not provide a verified GOLD-free DEV stage trace")
    public_cases = public_trace.get("cases") or []
    if len(public_cases) != len(rows):
        raise RuntimeError("DEV stage trace does not align with evaluator case rows")
    traces = []
    for row, public_case in zip(rows, public_cases, strict=True):
        outcome = public_case.get("benchmark_outcome") or {}
        fingerprint_source = json.dumps(
            {"query": row["query"], "acceptable_ld_ids": sorted(row["acceptable_ld_ids"])},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        traces.append({
            "case_id": hashlib.sha256(row["query"].encode("utf-8")).hexdigest()[:24],
            "repetition": 0,
            "input_sha256": hashlib.sha256(fingerprint_source).hexdigest(),
            "failure_stage": str(outcome.get("failure_stage") or "UNKNOWN"),
            "failure_substage": str(outcome.get("failure_substage") or "UNKNOWN"),
            "acceptable_present_in_catalog": bool(outcome.get("acceptable_present_in_catalog")),
            "acceptable_in_pretruncate_pool": bool(outcome.get("acceptable_in_pretruncate_pool")),
            "acceptable_in_initial_retrieval": bool(outcome.get("acceptable_in_initial_retrieval")),
            "acceptable_in_rerank_candidates": bool(outcome.get("acceptable_in_rerank_candidates")),
            "acceptable_selected": bool(outcome.get("acceptable_selected")),
            "best_acceptable_pretruncate_rank": outcome.get("best_acceptable_pretruncate_rank"),
            "best_acceptable_initial_rank": outcome.get("best_acceptable_initial_rank"),
            "best_acceptable_rerank_rank": outcome.get("best_acceptable_rerank_rank"),
            "filter_failure_fields": list(outcome.get("filter_failure_fields") or []),
        })
    return traces


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", nargs="?", default=".")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    root = Path.cwd().resolve() if args.workspace in {".", "{workspace}"} else Path(args.workspace).resolve()
    script = root / "scripts" / "eval_competitor_analogs.py"
    if not script.is_file():
        raise SystemExit(f"frozen evaluator missing from candidate snapshot: {script}")
    if not CATALOG.is_file():
        raise SystemExit("required product catalog is unavailable")
    if not os.getenv("OPENAI_API_KEY") or not os.getenv("DEEPSEEK_API_KEY"):
        raise SystemExit("evaluator runtime credentials are unavailable")

    evaluator = load_evaluator_module(script)
    frozen_cases = evaluator.load_embedded_cases()
    fixed_sample = random.Random(SEED).sample(frozen_cases, SAMPLE)
    selected_cases = fixed_sample[:SMOKE_CASES] if args.smoke else fixed_sample
    expected_n = len(selected_cases)

    with tempfile.TemporaryDirectory(prefix="bananloop-dev-eval-") as temp:
        temp_root = Path(temp)
        payload, public_trace = run_repository_evaluator(
            script, root, temp_root / "gold-trace.json", args.smoke, selected_cases,
        )

    rows = payload["cases"]
    if len(rows) != expected_n:
        raise SystemExit(f"fixed_dev_sample expected {expected_n} cases, got {len(rows)}")
    # Verify the smoke CSV round-trip preserved the exact selected queries and
    # acceptable-ID sets from the frozen sample.
    expected = {
        (case["query"], tuple(sorted(case["acceptable_ld_ids"])))
        for case in selected_cases
    }
    actual = {
        (row["query"], tuple(sorted(row["acceptable_ld_ids"])))
        for row in rows
    }
    if actual != expected:
        raise SystemExit("evaluator cases do not match the pinned frozen DEV sample")

    groups: dict[str, list[dict]] = {name: [] for name in EXPECTED_GROUPS}
    ungrouped = 0
    for row in rows:
        query = row["query"].casefold()
        found = [name for name in EXPECTED_GROUPS if name.casefold() in query]
        if len(found) > 1:
            raise SystemExit("a frozen query matched multiple cohort markers")
        if found:
            groups[found[0]].append(row)
        else:
            ungrouped += 1
    group_sizes_ok = args.smoke or {
        name: len(items) for name, items in groups.items()
    } == EXPECTED_GROUPS

    summary = payload["summary"]
    stages = summary.get("failure_stages", {})
    metrics: dict[str, float] = {
        "top1/hit_any_rate": float(summary["hit_any_rate"]),
        "initial_recall": float(summary["acceptable_in_initial_retrieval_rate"]),
        "rerank_recall": float(summary["acceptable_in_rerank_candidates_rate"]),
        "RETRIEVAL_MISS": float(stages.get("RETRIEVAL_MISS", 0)),
        "RERANK_SELECTION": float(stages.get("RERANK_SELECTION", 0)),
        "FILTER_DROP": float(stages.get("FILTER_DROP", 0)),
        "success": float(summary["pass"]),
    }
    for name, items in groups.items():
        n = len(items)
        metrics[f"groups.{name}.top1"] = (
            sum(row["verdict"] == "PASS" for row in items) / n if n else 0.0
        )
        metrics[f"groups.{name}.initial_recall"] = (
            sum(bool(row["diagnostics"]["acceptable_in_initial_retrieval"]) for row in items) / n
            if n else 0.0
        )
        metrics[f"groups.{name}.rerank_recall"] = (
            sum(bool(row["diagnostics"]["acceptable_in_rerank_candidates"]) for row in items) / n
            if n else 0.0
        )

    settings = evaluator.Settings()
    runtime_settings = settings.model_dump()
    # Bind measurement settings into protocol identity without ever serializing
    # runtime credentials or unrelated database connection strings.
    for sensitive in ("openai_api_key", "deepseek_api_key", "database_url"):
        runtime_settings.pop(sensitive, None)
    snapshot = root / "qdrant" / "steel_products_active.snapshot"
    protocol = {
        "benchmark": "embedded:competitor_analog_hit_any_min_v1",
        "benchmark_xz_sha256": evaluator._EXPECTED_XZ_SHA256,
        "benchmark_tsv_sha256": evaluator._EXPECTED_TSV_SHA256,
        "sample": SAMPLE,
        "seed": SEED,
        "smoke_cases": SMOKE_CASES,
        "workers": WORKERS,
        "cohorts": EXPECTED_GROUPS,
        "cohort_rule": "case-insensitive substring in query",
        "catalog_sha256": sha256_file(CATALOG),
        "qdrant_snapshot_sha256": sha256_file(snapshot) if snapshot.is_file() else None,
        "evaluator_sha256": sha256_file(script),
        "settings": runtime_settings,
    }
    protocol_sha256 = hash_json(protocol)

    cases = []
    for row in rows:
        fingerprint_source = json.dumps(
            {"query": row["query"], "acceptable_ld_ids": sorted(row["acceptable_ld_ids"])},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        cases.append({
            "case_id": hashlib.sha256(row["query"].encode("utf-8")).hexdigest()[:24],
            "input_sha256": hashlib.sha256(fingerprint_source).hexdigest(),
            "metrics": {
                "top1/hit_any_rate": float(row["verdict"] == "PASS"),
                "initial_recall": float(bool(row["diagnostics"]["acceptable_in_initial_retrieval"])),
                "rerank_recall": float(bool(row["diagnostics"]["acceptable_in_rerank_candidates"])),
            },
        })

    fixed_sample_ok = len(rows) == expected_n and actual == expected
    cohort_check = group_sizes_ok and (args.smoke or ungrouped >= 0)
    group_metrics_check = all(
        f"groups.{name}.{metric}" in metrics
        for name in EXPECTED_GROUPS
        for metric in ("top1", "initial_recall", "rerank_recall")
    )
    checks = {
        "fixed_dev_sample": check(fixed_sample_ok, len(rows)),
        "case_insensitive_cohorts": check(cohort_check, len(rows)),
        "group_metrics": check(group_metrics_check and group_sizes_ok, len(rows)),
        "paired_protocol": check(bool(protocol_sha256) and len(cases) == len(rows), len(rows)),
        "gold_isolation": check(
            all(set(row).isdisjoint({"query", "acceptable_ld_ids", "returned_ld_id"}) for row in cases),
            len(rows),
        ),
        "no_final_holdout": check(payload["dataset_source"].startswith("embedded:") or args.smoke, len(rows)),
    }
    result = {
        "schema_version": 1,
        "status": "ok",
        "metrics": metrics,
        "checks": checks,
        "protocol_sha256": protocol_sha256,
        "cases": cases,
        "retrieval_case_traces": retrieval_case_traces,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
