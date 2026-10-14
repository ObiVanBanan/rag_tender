from types import SimpleNamespace
from fastapi.testclient import TestClient

from nomenclature_matcher.api import create_app
from nomenclature_matcher.business_demo import build_demo_item, parameter_rows
from nomenclature_matcher.models import MatchResult, SearchCandidate, SelectedMatch


def test_parameter_decoding_units():
    rows = parameter_rows({"constraints":{"dn":50,"pn_min_mpa":1.6,"joining_type":"flanged"},
                           "hard_constraints":{"dn":50,"pn_min_mpa":1.6}})
    assert next(x for x in rows if x["key"]=="pn_min_mpa")["value"] == "1.6 МПа (PN16)"
    assert next(x for x in rows if x["key"]=="dn")["check"] == "Строгое условие"


def test_recommendations_not_equated_to_retrieval_candidates():
    a = SearchCandidate(ld_id=1, name="LD", article="LD-1", score=.031)
    b = SearchCandidate(ld_id=2, name="Другой LD", article="LD-2", score=.030)
    s = SelectedMatch(candidate_id=1, ld_id=1, name="LD", article="LD-1",
                      llm_confidence=.9, reason="подходит")
    m = MatchResult(query="кран DN50", status="MATCHED", score=.031,
                    ld_product=a, selected=[s], candidates=[a,b])
    dto = build_demo_item(m, 250)
    assert dto["recommended"][0]["article"] == "LD-1"
    assert dto["other_candidates"][0]["selection"] == "FOR_REVIEW"
    assert dto["metrics"]["retrieved_count"] == 2


class Runtime:
    settings = SimpleNamespace(api_max_batch_size=2, match_trace_enabled=False)
    def __init__(self):
        self.matcher = self
    def close(self): pass
    def ready(self): return True
    def match_one_hybrid_with_rerank(self, query):
        if query == "fail": raise RuntimeError("PRIVATE_PROVIDER_TOKEN")
        return MatchResult(query=query, status="NOT_FOUND", candidates=[])


def test_ui_and_demo_endpoint_error_redaction():
    app = create_app(runtime_factory=Runtime)
    with TestClient(app) as c:
        page = c.get("/demo")
        result = c.post("/v1/demo/match", json={"products":["unknown","fail"]})
        too_many = c.post("/v1/demo/match", json={"products":["a","b","c"]})
    assert page.status_code == 200 and "Подбор эквивалентов LD" in page.text
    assert [x["status"] for x in result.json()["results"]] == ["NOT_FOUND","ERROR"]
    assert "PRIVATE_PROVIDER_TOKEN" not in result.text
    assert too_many.status_code == 413
