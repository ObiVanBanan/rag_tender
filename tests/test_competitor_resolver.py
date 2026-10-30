import sqlite3
from types import SimpleNamespace

from nomenclature_matcher.competitor_resolver import CompetitorResolver


def settings(tmp_path):
    return SimpleNamespace(
        competitor_kb_path=str(tmp_path / "competitor.sqlite3"),
        competitor_catalog_registry_path="data/competitor_catalogs/sources.json",
    )


def web_debug(model: str):
    return {
        "accepted": True,
        "identity_verified": True,
        "pages": [
            {
                "target": f"https://manufacturer.example/product/{model}",
                "text": f"{model} exact product page",
            }
        ],
    }


def test_temper_catalog_schema_resolves_exact_articles_and_reuses_kb(tmp_path):
    resolver = CompetitorResolver(settings(tmp_path))

    cases = [
        ("TEMPER 29420125", 125, 2.5, "flanged", "full", "20"),
        ("TEMPER 28220300", 300, 1.6, "welded", "reduced", "20"),
        ("TEMPER 29266025", 25, 4.0, "welded", "full", "12Х18Н10Т"),
        ("TEMPER 28745015", 15, 2.5, "flanged", "reduced", "09Г2С"),
        ("TEMPER 28445025", 25, 2.5, "flanged", "reduced", "09Г2С"),
        ("TEMPER 29920100", 100, 2.5, None, "full", "20"),
    ]

    for query, dn, pn, joining, bore, grade in cases:
        result = resolver.resolve(query)
        assert result.status == "CATALOG_SCHEMA_RESOLVED"
        assert result.identity_level == "EXACT_PRODUCT"
        assert result.attributes()["dn"] == dn
        assert result.attributes()["pn_min_mpa"] == pn
        assert result.attributes().get("joining_type") == joining
        assert result.attributes()["bore_type"] == bore
        assert result.attributes()["body_material_grade"] == grade

    restarted = CompetitorResolver(settings(tmp_path))
    cached = restarted.resolve("TEMPER 29420125")
    assert cached.status == "KB_HIT"
    assert cached.identity_anchor == "29420125"
    assert cached.attributes()["dn"] == 125


def test_exact_article_does_not_match_as_substring(tmp_path):
    resolver = CompetitorResolver(settings(tmp_path))

    result = resolver.resolve("TEMPER 1294201259")

    assert result.status == "MISS"
    assert result.resolved is False


def test_unlisted_product_stays_miss(tmp_path):
    resolver = CompetitorResolver(settings(tmp_path))

    result = resolver.resolve("TEMPER 99999999")

    assert result.status == "MISS"
    assert result.resolved is False
    assert result.attributes() == {}


def test_family_only_marshal_query_never_becomes_exact_product(tmp_path):
    resolver = CompetitorResolver(settings(tmp_path))

    result = resolver.resolve("Кран шаровой MARSHAL 11с67п")

    assert result.status == "MISS"
    assert result.identity_level == "UNRESOLVED"
    assert result.resolved is False


def test_old_v1_family_collapsed_row_is_ignored(tmp_path):
    cfg = settings(tmp_path)
    db = cfg.competitor_kb_path

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE competitor_products (
                identity_key TEXT PRIMARY KEY,
                manufacturer TEXT,
                article TEXT,
                aliases_json TEXT NOT NULL,
                facts_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO competitor_products(
                identity_key, manufacturer, article, aliases_json, facts_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "marshal:11с67п",
                "MARSHAL",
                "11с67п",
                '["11с67п"]',
                '{"dn":{"value":999,"status":"VERIFIED","sources":[]}}',
            ),
        )

    resolver = CompetitorResolver(cfg)
    result = resolver.resolve(
        "Кран шаровой MARSHAL 11с67п GAS PRO 2ЦП.01.0.025.100"
    )

    assert result.status == "CATALOG_DESIGNATION_RESOLVED"
    assert result.resolved is True
    assert result.identity_key == "marshal:2цп010025100"
    assert result.attributes()["dn"] == 100
    assert result.attributes()["dn"] != 999


def test_web_learning_uses_full_variant_identity_not_family(tmp_path):
    resolver = CompetitorResolver(settings(tmp_path))
    query = "Кран шаровой MARSHAL 11с67п GAS PRO 2ЦП.01.0.025.100"

    learned = resolver.learn_from_web(
        query,
        {
            "product_type": "ball_valve",
            "dn": 100,
            "pn_min_mpa": 2.5,
            "joining_type": "welded",
        },
        {
            "accepted": True,
            "identity_verified": True,
            "pages": [
                {
                    "target": "https://manufacturer.example/2cp-01-0-025-100",
                    "text": "MARSHAL 11с67п GAS PRO 2ЦП.01.0.025.100 DN100 PN25",
                },
                {
                    "target": "https://manufacturer.example/11s67p",
                    "text": "Family page for MARSHAL 11с67п",
                },
            ],
        },
    )

    assert learned is not None
    assert learned.identity_anchor == "2цп010025100"
    assert learned.identity_key == "marshal:2цп010025100"
    assert learned.identity_level == "EXACT_PRODUCT"

    family = resolver.resolve("MARSHAL 11с67п")
    assert family.status == "MISS"

    cached = resolver.resolve(query)
    assert cached.status == "KB_HIT"
    assert cached.identity_anchor == "2цп010025100"


def test_family_only_web_evidence_is_not_persisted_for_exact_variant(tmp_path):
    resolver = CompetitorResolver(settings(tmp_path))

    learned = resolver.learn_from_web(
        "Кран шаровой MARSHAL 11с67п GAS PRO 2ЦП.01.0.025.100",
        {"dn": 100, "pn_min_mpa": 2.5},
        {
            "accepted": True,
            "identity_verified": True,
            "pages": [
                {
                    "target": "https://manufacturer.example/11s67p",
                    "text": "Generic MARSHAL 11с67п family page",
                }
            ],
        },
    )

    assert learned is None


def test_conflicting_supported_web_claims_abstain(tmp_path):
    resolver = CompetitorResolver(settings(tmp_path))

    first = resolver.learn_from_web(
        "ACME XZ-200",
        {"dn": 50, "pn_min_mpa": 1.6},
        web_debug("XZ-200"),
    )
    assert first is not None
    assert first.facts["dn"].status == "SUPPORTED"

    second = resolver.learn_from_web(
        "ACME XZ-200",
        {"dn": 80, "pn_min_mpa": 1.6},
        {
            "accepted": True,
            "identity_verified": True,
            "pages": [
                {
                    "target": "https://dealer.example/product/XZ-200",
                    "text": "XZ-200 DN80 PN16",
                }
            ],
        },
    )

    assert second is not None
    assert second.facts["dn"].status == "CONFLICTED"
    assert second.facts["dn"].value is None
    assert second.attributes().get("dn") is None
    assert second.facts["pn_min_mpa"].status == "SUPPORTED"
    assert second.facts["pn_min_mpa"].value == 1.6


def test_unverified_web_result_is_not_saved(tmp_path):
    resolver = CompetitorResolver(settings(tmp_path))

    learned = resolver.learn_from_web(
        "ACME XZ-101",
        {"dn": 80},
        {
            "accepted": False,
            "identity_verified": False,
            "pages": [{"target": "https://example.test/neighbor", "text": "DN80"}],
        },
    )

    assert learned is None
    assert resolver.resolve("ACME XZ-101").status == "MISS"



def test_marshal_designation_schema_resolves_exact_variant(tmp_path):
    resolver = CompetitorResolver(settings(tmp_path))

    reduced = resolver.resolve(
        "Кран шаровой MARSHAL 11с67п GAS PRO 2ЦП.01.1.016.050/040"
    )
    assert reduced.status == "CATALOG_DESIGNATION_RESOLVED"
    assert reduced.identity_level == "EXACT_PRODUCT"
    assert reduced.identity_anchor == "2цп011016050040"
    assert reduced.attributes()["dn"] == 50
    assert reduced.attributes()["pn_min_mpa"] == 1.6
    assert reduced.attributes()["joining_type"] == "welded"
    assert reduced.attributes()["bore_type"] == "reduced"
    assert reduced.attributes()["body_material_grade"] == "09Г2С"
    assert reduced.attributes()["control"] == "manual"
    assert reduced.attributes()["working_medium"] == "газ"

    full = resolver.resolve(
        "Кран шаровой MARSHAL 11с67п ЦП.00.3.025.100"
    )
    assert full.status == "CATALOG_DESIGNATION_RESOLVED"
    assert full.attributes()["dn"] == 100
    assert full.attributes()["pn_min_mpa"] == 2.5
    assert full.attributes()["joining_type"] == "welded"
    assert full.attributes()["bore_type"] == "full"
    assert full.attributes()["body_material_grade"] == "20"
    assert full.attributes()["control"] == "gearbox"


def test_marshal_combined_family_preserves_two_different_pipe_ends(tmp_path):
    resolver = CompetitorResolver(settings(tmp_path))

    result = resolver.resolve(
        "Кран шаровой MARSHAL 11с67п 2ЦПФ.00.1.016.050"
    )

    assert result.status == "CATALOG_DESIGNATION_RESOLVED"
    assert result.attributes()["dn"] == 50
    assert result.attributes().get("joining_type") == "mixed_flange_weld"


def test_also_designation_schema_resolves_official_model_structure(tmp_path):
    resolver = CompetitorResolver(settings(tmp_path))

    flanged = resolver.resolve("Кран шаровой ALSO КШ.Ф.080.16-01")
    assert flanged.status == "CATALOG_DESIGNATION_RESOLVED"
    assert flanged.identity_level == "EXACT_PRODUCT"
    assert flanged.attributes()["dn"] == 80
    assert flanged.attributes()["pn_min_mpa"] == 1.6
    assert flanged.attributes()["joining_type"] == "flanged"
    assert flanged.attributes()["bore_type"] == "reduced"
    assert flanged.attributes()["body_material_grade"] == "20"

    gas_full = resolver.resolve("Кран шаровой ALSO КШ.ФП.GAS.200.25-02")
    assert gas_full.status == "CATALOG_DESIGNATION_RESOLVED"
    assert gas_full.attributes()["dn"] == 200
    assert gas_full.attributes()["pn_min_mpa"] == 2.5
    assert gas_full.attributes()["joining_type"] == "flanged"
    assert gas_full.attributes()["bore_type"] == "full"
    assert gas_full.attributes()["body_material_grade"] == "09Г2С"
    assert gas_full.attributes()["working_medium"] == "газ"
    assert gas_full.attributes()["valve_type"] == "gas"


def test_also_unknown_connection_code_keeps_joining_unknown(tmp_path):
    resolver = CompetitorResolver(settings(tmp_path))

    result = resolver.resolve("Кран шаровой ALSO КШ.КПА.100.16-01")

    assert result.status == "CATALOG_DESIGNATION_RESOLVED"
    assert result.attributes()["dn"] == 100
    assert result.attributes()["pn_min_mpa"] == 1.6
    assert result.attributes().get("joining_type") is None



def test_temper_max_catalog_schema_resolves_without_identity_collapse(tmp_path):
    resolver = CompetitorResolver(settings(tmp_path))

    threaded = resolver.resolve("TEMPER 99020015 MAX")
    assert threaded.status == "CATALOG_SCHEMA_RESOLVED"
    assert threaded.identity_anchor == "99020015max"
    assert threaded.identity_key == "temper:99020015max"
    assert threaded.attributes()["dn"] == 15
    assert threaded.attributes()["pn_min_mpa"] == 4.0
    assert threaded.attributes()["joining_type"] == "threaded"
    assert threaded.attributes()["bore_type"] == "full"
    assert threaded.attributes()["working_medium"] == "газ"
    assert threaded.attributes()["valve_type"] == "gas"
    assert threaded.attributes().get("body_material_grade") is None

    welded = resolver.resolve("TEMPER 99220015 MAX")
    assert welded.status == "CATALOG_SCHEMA_RESOLVED"
    assert welded.identity_anchor == "99220015max"
    assert welded.attributes()["dn"] == 15
    assert welded.attributes()["pn_min_mpa"] == 4.0
    assert welded.attributes()["joining_type"] == "welded"
    assert welded.attributes()["bore_type"] == "full"
    assert welded.attributes()["working_medium"] == "газ"

    # The unsuffixed article is a different product and must not hit the MAX KB row.
    plain = resolver.resolve("TEMPER 99020015")
    assert plain.status == "MISS"
    assert plain.resolved is False


def test_temper_max_schema_is_conservative_when_catalog_is_ambiguous(tmp_path):
    resolver = CompetitorResolver(settings(tmp_path))

    large_welded = resolver.resolve("TEMPER 99220300 MAX")
    assert large_welded.status == "CATALOG_SCHEMA_RESOLVED"
    assert large_welded.attributes()["dn"] == 300
    assert large_welded.attributes().get("pn_min_mpa") is None
    assert large_welded.attributes()["joining_type"] == "welded"

    universal_flanged = resolver.resolve("TEMPER 99320065 MAX")
    assert universal_flanged.status == "CATALOG_SCHEMA_RESOLVED"
    assert universal_flanged.attributes()["dn"] == 65
    assert universal_flanged.attributes()["pn_min_mpa"] == 1.6
    assert universal_flanged.attributes()["joining_type"] == "flanged"
    assert universal_flanged.attributes()["bore_type"] == "full"
    assert universal_flanged.attributes().get("working_medium") is None



def test_also_welded_prefix_does_not_force_full_bore(tmp_path):
    resolver = CompetitorResolver(settings(tmp_path))

    result = resolver.resolve(
        "Кран шаровой под приварку стандартнопроходной "
        "КШ.П.Р.032.40-01 ALSO"
    )

    assert result.status == "CATALOG_DESIGNATION_RESOLVED"
    assert result.attributes()["dn"] == 32
    assert result.attributes()["pn_min_mpa"] == 4.0
    assert result.attributes()["joining_type"] == "welded"
    assert result.attributes()["bore_type"] == "reduced"


def test_marshal_official_actuator_code_coverage(tmp_path):
    import pytest
    resolver = CompetitorResolver(settings(tmp_path))
    cases = [
        ("0", "actuator_ready"),
        ("1", "manual"),
        ("3", "gearbox"),
        ("6", "pneumatic"),
        ("7", "hydraulic"),
        ("6(7)", "pneumohydraulic"),
        ("9", "electric"),
        ("10", "t_key"),
    ]
    for code, expected in cases:
        query = f"Кран шаровой MARSHAL 11с67п 2ЦФ.00.{code}.025.100"
        result = resolver.resolve(query)
        assert result.attributes()["control"] == expected, query
        assert result.attributes()["bore_type"] == "reduced"


def test_marshal_old_cached_unknown_drive_is_refreshed_from_catalog(tmp_path):
    from nomenclature_matcher.domain.competitor import ResolvedFact
    resolver = CompetitorResolver(settings(tmp_path))
    query = "MARSHAL 11с67п ЦФ.00.9.016.050"
    old = resolver.resolve(query)
    from dataclasses import replace
    obsolete = replace(old, facts={
        **(old.facts or {}),
        "control": ResolvedFact(None, "UNKNOWN", [{
            "evidence_scope": "nomenclature_schema",
            "source_type": "official_catalog_pdf"
        }]),
    })
    resolver.store.put(obsolete)
    upgraded = resolver.resolve(query)
    assert upgraded.status == "KB_HIT"
    assert upgraded.attributes()["control"] == "electric"


def test_also_ready_is_not_equivalent_to_installed_gearbox(tmp_path):
    resolver = CompetitorResolver(settings(tmp_path))
    full = resolver.resolve("Кран шаровой ALSO КШ.ФПР.GAS.200.25-02")
    assert full.attributes()["bore_type"] == "full"
    assert full.attributes()["control"] == "gearbox_ready"
    flanged = resolver.resolve("Кран шаровой ALSO КШ.Ф.П.Р.400.16-01")
    assert flanged.attributes()["bore_type"] == "full"
    assert flanged.attributes()["control"] == "gearbox_ready"
    unknown = resolver.resolve("Кран шаровой ALSO КШ.КПА.100.16-01")
    assert unknown.attributes().get("bore_type") is None
