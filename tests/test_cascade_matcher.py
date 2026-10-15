"""CSV-first RAG fallback behaviour; no paid inference in CI."""
from types import SimpleNamespace

import pytest

from nomenclature_matcher.cascade_matcher import CsvFirstRagMatcher
from nomenclature_matcher.models import MatchResult, SearchCandidate, SelectedMatch
from nomenclature_matcher.business_demo import build_demo_item, business_page
from nomenclature_matcher.production import _validate_runtime_settings


class FakeMatcher:
    def __init__(self, result=None, error=None):
        self.calls = []
        self.result = result
        self.error = error
        self.index = SimpleNamespace(identity_for=lambda source: None)
        self.competitor_lookup = None

    def match_one_hybrid_with_rerank(self, query):
        self.calls.append(query)
        if self.error:
            raise self.error
        return self.result


def cascade(csv_result, rag_result=None, error=None):
    csv = FakeMatcher(csv_result)
    rag = FakeMatcher(rag_result, error)
    settings = SimpleNamespace(match_backend="hybrid")
    matcher = CsvFirstRagMatcher(settings, rag_matcher=rag, csv_matcher=csv)
    return matcher, csv, rag


def test_csv_hit_never_pays_for_rag():
    hit = MatchResult(query="known", status="MATCHED", query_interpretation={"csv_backend": True})
    matcher, csv, rag = cascade(hit)
    result = matcher.match_one_hybrid_with_rerank("known")
    assert result is hit
    assert csv.calls == ["known"]
    assert rag.calls == []
    assert build_demo_item(result, 1)["match_source"] == "CSV_MAPPING"


def test_csv_miss_queries_native_rag_and_ui_identifies_source():
    miss = MatchResult(query="new item", status="NOT_FOUND", reason="CSV_MAPPING_NO_VERIFIED_IDENTITY")
    hit = SearchCandidate(ld_id=101, name="Кран шаровой LD Ду25", article="LD-101", score=0.45, dn=25)
    selected = SelectedMatch(candidate_id=1, article="LD-101", name="Кран шаровой LD Ду25",
                             llm_confidence=0.6, reason="Возможный аналог", ld_id=101)
    rag_result = MatchResult(
        query="new item", status="MATCHED",
        candidates=[hit], selected=[selected], ld_product=hit,
        query_interpretation={"constraints": {"dn": 25}},
    )
    matcher, csv, rag = cascade(miss, rag_result)
    result = matcher.match_one_hybrid_with_rerank("new item")
    assert csv.calls == ["new item"]
    assert rag.calls == ["new item"]
    assert result.query_interpretation["csv_fallback"] is True
    assert result.query_interpretation["constraints"] == {"dn": 25}
    assert "csv_fallback" not in rag_result.query_interpretation
    dto = build_demo_item(result, 2.0)
    assert dto["match_source"] == "RAG_FALLBACK"
    assert dto["top_candidates"][0]["article"] == "LD-101"
    assert "RAG" in dto["message"]


def test_no_csv_then_no_rag_is_not_found_not_csv_positive():
    miss = MatchResult(query="never", status="NOT_FOUND")
    rag_miss = MatchResult(query="never", status="NOT_FOUND", query_interpretation={})
    matcher, _, rag = cascade(miss, rag_miss)
    dto = build_demo_item(matcher.match_one_hybrid_with_rerank("never"), 1)
    assert rag.calls == ["never"]
    assert dto["status"] == "NOT_FOUND"
    assert dto["match_source"] == "RAG_FALLBACK"


def test_missing_required_parameters_never_call_rag():
    safety = MatchResult(
        query="Кран шаровый 11Б27П Ду20 Ру16",
        status="INSUFFICIENT_PARAMETERS",
        query_interpretation={"csv_backend": True, "missing_fields": ["thread_type", "thread_size"]},
    )
    matcher, _, rag = cascade(safety)
    dto = build_demo_item(matcher.match_one_hybrid_with_rerank(safety.query), 1)
    assert rag.calls == []
    assert dto["status"] == "INSUFFICIENT_PARAMETERS"


def test_rag_provider_failure_is_not_misreported_as_no_match():
    matcher, _, rag = cascade(
        MatchResult(query="x", status="NOT_FOUND"),
        error=ConnectionError("Provider unavailable"),
    )
    with pytest.raises(ConnectionError, match="Provider unavailable"):
        matcher.match_one_hybrid_with_rerank("x")
    assert rag.calls == ["x"]


def test_hybrid_demo_view_explains_both_backends():
    runtime = SimpleNamespace(settings=SimpleNamespace(match_backend="hybrid"))
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=runtime)))
    html = business_page(req).body.decode("utf-8")
    assert "ЭКСПЕРИМЕНТ · CSV + RAG" in html
    assert "Если кандидатов нет — запускаем RAG" in html
    assert "RAG_FALLBACK" in html
    assert 'id="history-open"' in html
    assert 'id="append-open"' in html


def test_hybrid_requires_real_qdrant_dependencies_and_csv(tmp_path):
    from nomenclature_matcher.csv_mapping import CsvMappingIndex
    from test_csv_demo_integration import settings as csv_fixture
    missing = tmp_path / "empty"
    missing.mkdir()
    settings = SimpleNamespace(match_backend="hybrid", csv_mapping_dir=str(missing),
                               openai_api_key="", deepseek_api_key="",
                               product_csv_path="/missing-products.csv")
    with pytest.raises(RuntimeError, match="Missing CSV mapping files"):
        _validate_runtime_settings(settings)
    for filename in CsvMappingIndex.FILES:
        (missing / filename).write_text("empty\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        _validate_runtime_settings(settings)
