import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _adapter():
    path = Path(__file__).parents[1] / ".bananloop_eval" / "evaluate.py"
    spec = importlib.util.spec_from_file_location("bananloop_eval_adapter", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_protocol_hash_tracks_measurement_identity_not_candidate_settings(tmp_path, monkeypatch):
    adapter = _adapter()
    catalog = tmp_path / "catalog.csv"
    script = tmp_path / "evaluator.py"
    adapter_file = tmp_path / "adapter.py"
    snapshot = tmp_path / "qdrant.snapshot"
    for path, contents in (
        (catalog, "catalog"),
        (script, "evaluator"),
        (adapter_file, "adapter"),
        (snapshot, "snapshot"),
    ):
        path.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(adapter, "CATALOG", catalog)
    evaluator = SimpleNamespace(
        _EXPECTED_XZ_SHA256="f" * 64,
        _EXPECTED_TSV_SHA256="e" * 64,
    )

    first = adapter.build_protocol_sha256(evaluator, script, adapter_file, snapshot)
    # Tunable retrieval settings are intentionally absent from protocol inputs.
    first_candidate_settings = {"hybrid_rerank_limit": 20}
    second_candidate_settings = {"hybrid_rerank_limit": 40}
    second = adapter.build_protocol_sha256(evaluator, script, adapter_file, snapshot)

    assert first_candidate_settings != second_candidate_settings
    assert first == second


def test_invalid_baseline_when_pipeline_cases_fail():
    adapter = _adapter()
    passing_checks = {name: {"passed": True} for name in adapter.REQUIRED_CHECKS}

    assert adapter.evaluation_status(passing_checks, fail_pipeline=0) == "ok"
    assert adapter.evaluation_status(passing_checks, fail_pipeline=1) == "invalid"

    failing_checks = {**passing_checks, "fixed_dev_sample": {"passed": False}}
    assert adapter.evaluation_status(failing_checks, fail_pipeline=0) == "invalid"


def test_adapter_reduces_public_dev_trace_to_hashed_stage_evidence():
    adapter = _adapter()
    rows = [{
        "query": "DEV query text",
        "acceptable_ld_ids": [42, 43],
    }]
    trace = {
        "artifact_type": "dev_stage_trace",
        "contains_gold_ids": False,
        "cases": [{
            "benchmark_outcome": {
                "failure_stage": "RETRIEVAL_MISS",
                "failure_substage": "MODALITY_POOL_MISS",
                "acceptable_present_in_catalog": True,
                "acceptable_in_pretruncate_pool": False,
                "acceptable_in_initial_retrieval": False,
                "acceptable_in_rerank_candidates": False,
                "acceptable_selected": False,
                "best_acceptable_pretruncate_rank": None,
                "best_acceptable_initial_rank": None,
                "best_acceptable_rerank_rank": None,
                "filter_failure_fields": [],
            }
        }],
    }

    result = adapter.build_retrieval_case_traces(rows, trace)

    assert len(result) == 1
    assert result[0]["failure_stage"] == "RETRIEVAL_MISS"
    assert result[0]["acceptable_present_in_catalog"] is True
    assert "case_id" in result[0] and len(result[0]["input_sha256"]) == 64
    assert "query" not in result[0]
    assert "acceptable_ld_ids" not in result[0]
    assert "42, 43" not in repr(result)


def test_adapter_requests_public_trace_without_running_repository_benchmark(tmp_path):
    adapter = _adapter()
    script = tmp_path / "fake_evaluator.py"
    script.write_text(
        "import json, pathlib, sys\n"
        "args=sys.argv\n"
        "out=pathlib.Path(args[args.index('--output') + 1])\n"
        "trace=pathlib.Path(args[args.index('--public-trace-output') + 1])\n"
        "out.write_text(json.dumps({'cases': []}))\n"
        "trace.write_text(json.dumps({'artifact_type': 'dev_stage_trace', 'contains_gold_ids': False, 'cases': []}))\n",
        encoding="utf-8",
    )

    result, public_trace = adapter.run_repository_evaluator(
        script, tmp_path, tmp_path / "gold.json", False, [],
    )

    assert result == {"cases": []}
    assert public_trace["artifact_type"] == "dev_stage_trace"
    assert public_trace["contains_gold_ids"] is False
