import pytest

from scripts.compare_eval_reports import compare_reports


def report(statuses, *, ds="embedded:competitor_analog_hit_any_min_v1"):
    return {
        "dataset_source": ds,
        "summary": {"evaluated_queries": len(statuses)},
        "cases": [{"query": f"case_{idx}", "acceptable_ld_ids": [idx],
                   "verdict": value} for idx, value in enumerate(statuses)],
    }


def test_candidate_may_improve_without_losing_previous_passes():
    result = compare_reports(
        report(["PASS", "FAIL_NOT_FOUND"]),
        report(["PASS", "PASS"]),
        expected_cases=2,
    )
    assert result["gain"] == 1
    assert result["no_metric_drop"]
    assert result["no_case_regressions"]


def test_decline_is_detected_and_regressed_cases_enumerated():
    result = compare_reports(
        report(["PASS", "PASS"]),
        report(["FAIL_WRONG_LD", "PASS"]),
        expected_cases=2,
    )
    assert result["gain"] == -1
    assert not result["no_metric_drop"]
    assert result["regressed_queries"] == ["case_0"]


def test_cohort_or_gold_change_is_not_compared():
    x=report(["PASS","PASS"])
    y=report(["PASS","PASS"])
    y["cases"][0]["acceptable_ld_ids"] = [999]
    with pytest.raises(ValueError,match="GOLD"):
        compare_reports(x,y,expected_cases=2)
    with pytest.raises(ValueError,match="Expected 2 cases"):
        compare_reports(x,report(["PASS"]),expected_cases=2)
    with pytest.raises(ValueError,match="mapping"):
        compare_reports(x,report(["PASS","PASS"],ds="other"),expected_cases=2)
