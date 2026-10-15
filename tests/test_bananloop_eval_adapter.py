import importlib.util
from pathlib import Path


def _adapter():
    path = Path(__file__).parents[1] / ".bananloop_eval" / "evaluate.py"
    spec = importlib.util.spec_from_file_location("bananloop_eval_adapter", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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
