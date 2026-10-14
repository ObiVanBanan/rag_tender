"""Offline regression comparison must not leak GOLD to either matcher or mask regressions."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from compare_regression_outputs import (  # noqa: E402
    allowed_sparse_refusal, classify, compare, evaluate, stage_of_failure,
    technical_rejection_evidence
)
from run_evolution_ab import load_cases, HISTORIC_REF, TENDER_GOLD_REF  # noqa: E402


def case(query="Кран шаровой DN50 PN16",positive=7):
    return {"id":"test","query":query,"split":"CORE","acceptable_ld_ids":[positive]}


def response(query="Кран шаровой DN50 PN16",status="MATCHED",selected=7,reason="",trace=None,candidates=None):
    debug={"reason":reason,"selected":[{"ld_id":selected}] if selected is not None else [],
           "candidates":[{"ld_id":x} for x in (candidates or [])]}
    if trace is not None:
        debug["query_interpretation"]={"retrieval_trace":trace}
    return {"query":query,"status":status,"debug":debug}


def test_identical_query_order_required_even_when_same_length():
    cases=[case("Кран DN50"),case("Кран DN25")]
    results=[response("Кран DN25"),response("Кран DN50")]
    with pytest.raises(ValueError,match="Order"):
        evaluate(cases,results)


def test_sparse_refusal_is_intentional_not_success_and_not_overridden():
    q="фильтр Ду50"
    res=response(q,status="NOT_FOUND",selected=None,
                 reason="QUERY_REJECTED: Недостаточно различающих характеристик для выбора")
    assert allowed_sparse_refusal(q,res)
    row=classify(case(q),res)
    assert row["verdict"]=="INTENTIONAL_SPARSE_REFUSAL"
    assert row["failure_stage"]=="POLICY_REFUSAL"
    q2="кран шаровый Ду150"
    assert allowed_sparse_refusal(q2,response(q2,status="NOT_FOUND",selected=None,reason=res["debug"]["reason"]))
    q3="кран шаровый DN50 PN16"
    assert not allowed_sparse_refusal(q3,response(q3,status="NOT_FOUND",selected=None,reason=res["debug"]["reason"]))


def test_flange_pnd_candidate_dropped_in_prefilter_is_distinguished_from_retrieval():
    trace={"technical_prefilter":{"rows":[{"ld_id":7,"hard_eligible":False},
                                             {"ld_id":15,"hard_eligible":True}]},
           "initial_candidate_ids":[15], "rerank_candidate_ids":[15]}
    res=response("Фланец стальной Ду80 под втулку ПНД Ду90",status="NOT_FOUND",
                 selected=None,trace=trace,candidates=[15])
    assert stage_of_failure(res,{7})=="TECHNICAL_PREFILTER_DROP"


def test_eligible_candidate_can_be_lost_by_reranker_or_hard_filter():
    trace={"technical_prefilter":{"rows":[{"ld_id":7}]},
           "initial_candidate_ids":[7,15],"rerank_candidate_ids":[15]}
    assert stage_of_failure(response(status="MATCHED",selected=15,trace=trace),{7})=="HARD_FILTER_DROP"
    trace["rerank_candidate_ids"]=[7,15]
    assert stage_of_failure(response(status="MATCHED",selected=15,trace=trace),{7})=="RERANK_NOT_SELECTED"


def test_no_gold_in_wide_pool_is_retrieval_miss():
    trace={"technical_prefilter":{"rows":[{"ld_id":15}]},
           "initial_candidate_ids":[15], "rerank_candidate_ids":[15]}
    assert stage_of_failure(response(status="MATCHED",selected=15,trace=trace),{7})=="RETRIEVAL_MISS"


def test_alternative_ld_is_unverified_not_immediately_false_match():
    row=classify(case(),response(selected=44))
    assert row["verdict"]=="OTHER_LD_REQUIRES_REVIEW"


def test_frozen100_hard_gate_blocks_case_regression_even_when_top1_ties():
    cases=[case("Кран DN50"),case("Кран DN25")]
    old=evaluate(cases,[response("Кран DN50",selected=7),response("Кран DN25",selected=1)])
    new=evaluate(cases,[response("Кран DN50",selected=1),response("Кран DN25",selected=7)])
    verdict=compare(old,new,frozen_guard=True)
    assert verdict["old_exact"]==verdict["new_exact"]==1
    assert not verdict["frozen100_acceptable"]
    assert verdict["regressed_case_ids"]==["test"]
    # Query cohorts must be identical in shape as well as size.
    with pytest.raises(ValueError,match="Cohort"):
        other=evaluate([case("Different")],[response("Different",selected=7)])
        compare(old,other)


def test_historic_tender20_source_is_exact_git_revision(tmp_path):
    baseline=tmp_path/"historic"
    (baseline/"data").mkdir(parents=True)
    payload={"cases":[{"id":f"tender_v1_{i:03d}","query":f"Query {i}",
                      "split":"CORE","known_positive_ids":[i]} for i in range(20)]}
    (baseline/"data/tender_queries_v1_harness_cases.json").write_text(json.dumps(payload))
    cases=load_cases("tender20",baseline/"data/tender_queries_v1_harness_cases.json")
    assert len(cases)==20
    assert cases[0]["acceptable_ld_ids"]==[0]
    assert HISTORIC_REF == "336d7c08cbface23afb0cbd6ae83736e294d870f"
    assert TENDER_GOLD_REF == "e1661896e8d0c7fbb18c02adb4abb9a1d93b4d2f"
    payload["cases"].pop()
    (baseline/"data/tender_queries_v1_harness_cases.json").write_text(json.dumps(payload))
    with pytest.raises(ValueError,match="instead of 20"):
        load_cases("tender20",baseline/"data/tender_queries_v1_harness_cases.json")


def test_evidence_attributes_offline_technical_conflicts_to_known_candidate():
    trace = {
        "technical_prefilter": {"rows": [
            {"ld_id":7, "original_rank":4,"hard_eligible":False,
             "checks":{"body_material":"mismatch:polyethylene vs steel",
                       "dn":"match"},"selected":False},
            {"ld_id":15, "hard_eligible":True,
             "checks":{"body_material":"match"},"selected":True},
        ]},
        "initial_candidate_ids":[15],
        "rerank_candidate_ids":[15],
    }
    res=response("Фланец стальной Ду80 под втулку ПНД Ду90",status="NOT_FOUND",
                 selected=None,trace=trace,candidates=[15])
    evidence=technical_rejection_evidence(res,{7})
    assert len(evidence)==1
    assert evidence[0]["hard_eligible"] is False
    assert "body_material" in evidence[0]["soft_conflicts"]
    assert "dn" not in evidence[0]["soft_conflicts"]


def test_tender20_labels_must_be_supplied_independently_of_old_algorithm():
    with pytest.raises(ValueError,match="explicit"):
        load_cases("tender20")
