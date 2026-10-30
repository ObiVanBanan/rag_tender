from nomenclature_matcher.query_signals import exact_product_identity_anchors


def test_exact_variant_anchor_excludes_family_only_token():
    anchors = exact_product_identity_anchors(
        "Кран шаровой MARSHAL 11с67п GAS PRO 2ЦП.01.0.025.100"
    )

    assert anchors[0] == "2цп010025100"
    assert "11с67п" not in anchors


def test_exact_variant_anchor_handles_parenthesized_marshal_code():
    anchors = exact_product_identity_anchors(
        "Кран шаровой MARSHAL 11с67п GAS PRO 2ЦФ.00.6(7).025.080"
    )

    assert anchors[0] == "2цф0067025080"


def test_exact_variant_anchor_handles_also_and_temper_articles():
    assert exact_product_identity_anchors(
        "Кран шаровой ALSO КШ.ФП.GAS.200.25-02"
    )[0] == "кшфпgas2002502"
    assert "29420125" in exact_product_identity_anchors("TEMPER 29420125")


def test_dn_pn_notation_is_not_product_identity():
    anchors = exact_product_identity_anchors(
        "Кран шаровой 11с67п 2ЦФ.00.1 DN65/50 PN25"
    )

    assert "dn6550" not in anchors
    assert "pn25" not in anchors
    assert "2цф001" in anchors



def test_temper_max_suffix_is_part_of_exact_identity():
    max_anchors = exact_product_identity_anchors("TEMPER 99020015 MAX")
    plain_anchors = exact_product_identity_anchors("TEMPER 99020015")

    assert max_anchors[0] == "99020015max"
    assert "99020015" in max_anchors
    assert "99020015max" not in plain_anchors
