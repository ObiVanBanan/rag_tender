from types import SimpleNamespace

from scripts.eval_competitor_analogs import (
    _assert_public_trace_has_no_gold,
    _diagnostics,
    _public_case_trace,
)


def _result(retrieval_trace):
    return SimpleNamespace(
        query_interpretation={
            "competitor_resolution": {
                "status": "CATALOG_DESIGNATION_RESOLVED",
                "identity_key": "marshal:example",
                "facts": {},
            },
            "constraints": {"dn": 100},
            "hard_constraints": {"dn": None},
            "retrieval_trace": retrieval_trace,
        },
        reason="",
        status="MATCHED",
        ld_product=SimpleNamespace(ld_id=999),
    )


def test_diagnostics_distinguishes_rrf_truncation_from_pool_miss():
    case = {"query": "competitor example", "acceptable_ld_ids": [42]}
    result = _result(
        {
            "retriever": {
                "rrf_pool": [
                    {"rank": 1, "ld_id": 10},
                    {"rank": 21, "ld_id": 42},
                ]
            },
            "initial_candidate_ids": [10],
            "rerank_candidate_ids": [10],
            "selected_ld_ids": [999],
        }
    )

    diagnostics = _diagnostics(case, result, "FAIL_WRONG_LD")

    assert diagnostics["failure_stage"] == "RETRIEVAL_MISS"
    assert diagnostics["failure_substage"] == "RRF_TRUNCATION"
    assert diagnostics["best_acceptable_pretruncate_rank"] == 21
    assert diagnostics["best_acceptable_initial_rank"] is None


def test_public_trace_keeps_stage_labels_but_never_gold_ids():
    case = {"query": "competitor example", "acceptable_ld_ids": [42]}
    result = _result(
        {
            "strategy": "competitor_resolved_technical_plus_catalog",
            "retriever": {
                "rrf_pool": [
                    {"rank": 1, "ld_id": 10},
                    {"rank": 2, "ld_id": 42},
                ]
            },
            "initial_candidate_ids": [10],
            "rerank_candidate_ids": [10],
            "selected_ld_ids": [999],
            "reranker_selected": [
                {
                    "candidate_id": 1,
                    "ld_id": 999,
                    "confidence": 0.8,
                    "reason": "selected",
                }
            ],
        }
    )
    diagnostics = _diagnostics(case, result, "FAIL_WRONG_LD")

    public = _public_case_trace(case, result, diagnostics)
    _assert_public_trace_has_no_gold(public)

    serialized = repr(public)
    assert "acceptable_ld_ids" not in serialized
    assert "returned_ld_id" not in serialized
    assert "rerank_candidate_ids" not in serialized
    assert '"ld_id"' not in serialized
    assert public["benchmark_outcome"]["failure_stage"] == "RETRIEVAL_MISS"
    assert "acceptable_in_pretruncate_pool" not in public["benchmark_outcome"]



def test_diagnostics_marks_technical_prefilter_drop():
    case = {"query": "competitor example", "acceptable_ld_ids": [42]}
    result = _result(
        {
            "retriever": {
                "rrf_pool": [
                    {"rank": 1, "ld_id": 10},
                    {"rank": 21, "ld_id": 42},
                ]
            },
            "technical_prefilter": {
                "applied": True,
                "selected_ids": [10],
            },
            "initial_candidate_ids": [10],
            "rerank_candidate_ids": [10],
            "selected_ld_ids": [999],
        }
    )

    diagnostics = _diagnostics(case, result, "FAIL_WRONG_LD")

    assert diagnostics["failure_stage"] == "RETRIEVAL_MISS"
    assert diagnostics["failure_substage"] == "TECHNICAL_PREFILTER_DROP"
