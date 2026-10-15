"""Offline CSV-mapping demo integration contract (never uses GOLD rows)."""
from __future__ import annotations

import csv
from types import SimpleNamespace

import pytest

from nomenclature_matcher.csv_mapping import CsvMappingMatcher, CsvMappingIndex
from nomenclature_matcher.business_demo import (
    _keep_csv_identity, build_demo_item, business_page,
)


@pytest.fixture()
def settings(tmp_path):
    data = tmp_path / "csv_mappings"
    data.mkdir()
    definitions = [
        (
            "competitor_ld_mapping.csv",
            ["competitor_article", "c_name", "c_dn", "c_pn", "c_thread_type",
             "ld_article", "name", "dn", "pn", "thread_type", "url"],
            [
                {
                    "competitor_article": "SVB-0001-000025",
                    "c_name": "Кран шаровой латунный STOUT Ду25 Ру40 ВР/ВР",
                    "c_dn": "25", "c_pn": "40", "c_thread_type": "Внутренняя/Внутренняя",
                    "ld_article": "LD 47.301.25",
                    "name": "Кран шаровой латунный LD Ду25 Ру40 ВР/ВР",
                    "dn": "25", "pn": "40", "thread_type": "Внутренняя/Внутренняя",
                    "url": "https://example.org/products/100--ld/",
                }
            ],
        ),
        (
            "butterfly_mapping_results.csv",
            ["steel_marking", "steel_dn", "steel_pn", "steel_connection",
             "steel_control", "steel_material", "ld_marking", "ld_dn",
             "ld_pn", "ld_connection", "ld_control", "ld_material"],
            [
                {
                    "steel_marking": "PALUR-ZD-3EX-DN1000-PN16-1N-FL-EL-U1",
                    "steel_dn": "1000", "steel_pn": "16",
                    "steel_connection": "Фланцевое",
                    "steel_control": "Под электропривод",
                    "steel_material": "Сталь 20",
                    "ld_marking": "6-01000.16-1120-000-E0",
                    "ld_dn": "1000", "ld_pn": "16",
                    "ld_connection": "Фланцевое",
                    "ld_control": "Под электропривод",
                    "ld_material": "Сталь 20",
                }
            ],
        ),
        (
            "mapping_results.csv",
            ["steel_article", "steel_name", "steel_dn", "steel_pn_bar",
             "steel_connection", "steel_control", "steel_medium",
             "steel_body_material", "ld_article", "ld_name", "ld_dn",
             "ld_pn_mpa", "ld_connection", "ld_control", "ld_medium",
             "ld_url"],
            [
                {
                    "steel_article": "1184399",
                    "steel_name": "Кран шаровой Temper DN80 PN16 фланцевый",
                    "steel_dn": "80", "steel_pn_bar": "16",
                    "steel_connection": "фланцевое", "steel_control": "ручное",
                    "steel_medium": "жидкость", "steel_body_material": "сталь 20",
                    "ld_article": "11100800162MULD000003000",
                    "ld_name": "Кран шаровой LD Ду80 Ру1,6МПа фланцевый",
                    "ld_dn": "80", "ld_pn_mpa": "16",
                    "ld_connection": "фланцевое", "ld_control": "ручное",
                    "ld_medium": "жидкость",
                    "ld_url": "https://example.org/products/15870--ld/",
                },
                {
                    "steel_article": "1184399",
                    "steel_name": "Кран шаровой Temper DN80 PN16 фланцевый",
                    "steel_dn": "80", "steel_pn_bar": "16",
                    "steel_connection": "фланцевое", "steel_control": "ручное",
                    "steel_medium": "жидкость", "steel_body_material": "сталь 20",
                    "ld_article": "BAD-DN50",
                    "ld_name": "Кран шаровой LD Ду50 Ру16 фланцевый",
                    "ld_dn": "50", "ld_pn_mpa": "16",
                    "ld_connection": "фланцевое", "ld_control": "ручное",
                    "ld_medium": "жидкость",
                    "ld_url": "https://example.org/products/15871--ld/",
                },
            ],
        ),
    ]
    for name, fields, rows in definitions:
        with (data / name).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=fields,
                delimiter=";" if name.startswith("butterfly") else ",",
            )
            writer.writeheader()
            writer.writerows(rows)
    return SimpleNamespace(csv_mapping_dir=str(data), match_backend="csv_mapping")


def test_csv_demo_returns_real_selectable_candidates(settings):
    matcher = CsvMappingMatcher(settings)
    result = matcher.match_one_hybrid_with_rerank("1184399")
    assert result.status == "MATCHED"
    assert len(result.candidates) == 1  # incompatible LD DN50 pair is rejected
    assert len(result.selected) == 1
    dto = build_demo_item(result, 2.0)
    assert dto["match_source"] == "CSV_MAPPING"
    assert dto["top_candidates"][0]["article"] == "11100800162MULD000003000"
    assert dto["mapping_source"] == "mapping_results.csv"
    assert dto["metrics"]["retrieval_score"] is None
    assert "взаимозаменяемость" in dto["message"]


def test_csv_no_match_and_user_safety_gate(settings):
    matcher = CsvMappingMatcher(settings)
    assert matcher.match_one_hybrid_with_rerank("UNSEEN-ARTICLE-999").status == "NOT_FOUND"
    incomplete = matcher.match_one_hybrid_with_rerank("Кран шаровый 11Б27П Ду20 Ру16")
    assert incomplete.status == "INSUFFICIENT_PARAMETERS"
    assert "thread_type" in incomplete.query_interpretation["missing_fields"]


def test_user_corrected_query_retains_source_article(settings):
    matcher = CsvMappingMatcher(settings)
    runtime = SimpleNamespace(settings=settings, matcher=matcher)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=runtime)))
    fixed = _keep_csv_identity(request, "1184399", "Кран шаровый Ду80 Ру16")
    assert "1184399" in fixed
    assert matcher.match_one_hybrid_with_rerank(fixed).status == "MATCHED"
    wrong = _keep_csv_identity(request, "1184399", "Кран шаровый Ду50 Ру16")
    assert matcher.match_one_hybrid_with_rerank(wrong).status == "NOT_FOUND"


def test_csv_demo_page_shows_real_csv_examples(settings):
    matcher = CsvMappingMatcher(settings)
    runtime = SimpleNamespace(settings=settings, matcher=matcher)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=runtime)))
    page = business_page(request).body.decode("utf-8")
    assert "ЭКСПЕРИМЕНТ · ПОИСК ПО CSV-МАППИНГАМ" in page
    assert 'data-q="1184399"' in page
    assert 'data-q="SVB-0001-000025"' in page
    assert 'id="history-open"' in page
    assert 'id="append-open"' in page
