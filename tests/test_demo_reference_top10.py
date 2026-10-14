"""Verify the business review actually exposes selectable top-10 alternatives."""
from nomenclature_matcher.business_demo import build_demo_item
from nomenclature_matcher.demo_feedback import DemoFeedbackStore, ReviewConflict
from nomenclature_matcher.models import MatchResult, SearchCandidate, SelectedMatch

import pytest


def fixture_match(n=13):
    products=[
        SearchCandidate(
            ld_id=8000+i,name=f"Кран шаровый LD Ду{80 if i<8 else 100} Ру16 №{i}",
            article=f"LD-{8000+i}",score=1-i/30,
            dn=80 if i<8 else 100,pn="1,6",
        )
        for i in range(n)
    ]
    selected=[
        SelectedMatch(candidate_id=i+1,ld_id=products[i].ld_id,
                      name=products[i].name,article=products[i].article,
                      llm_confidence=.7,reason=f"rank {i+1}")
        for i in range(2)
    ]
    return MatchResult(
        query="Кран шаровый Ду80 Ру16 фланцевый для воды",
        status="MATCHED",score=products[0].score,
        ld_product=products[0],selected=selected,candidates=products,
        query_interpretation={
            "constraints":{"product_type":"ball_valve","dn":80},
            "hard_constraints":{"dn":80},
        },
    )


def test_top_ten_candidates_are_distinct_ranked_and_actionable():
    result=build_demo_item(fixture_match(),12.0)
    assert len(result["recommended"])==1
    assert len(result["other_candidates"])==9
    assert len(result["candidates"])==10
    assert [x["rank"] for x in result["candidates"]]==list(range(1,11))
    assert len({x["ld_id"] for x in result["candidates"]})==10
    assert result["recommended"][0]["ld_id"]==8000
    assert result["other_candidates"][0]["ld_id"]==8001
    assert result["other_candidates"][0]["selection"]=="FOR_REVIEW"
    assert result["candidates"][1]["review_gate"]=="CHECKS_PASSED"
    assert result["candidates"][8]["review_gate"]=="BLOCKED"
    assert DemoFeedbackStore._candidate(result,"SELECTED_OTHER",8001,False)==8001
    with pytest.raises(ReviewConflict):
        DemoFeedbackStore._candidate(result,"SELECTED_OTHER",8008,True)
    # Manual override is possible only with an explicit logged mismatch waiver;
    # it does not convert a known technical mismatch into a safe model match.
    assert DemoFeedbackStore._candidate(result,"SELECTED_OTHER",8008,True,True)==8008
    with pytest.raises(ReviewConflict):
        DemoFeedbackStore._candidate(result,"ACCEPTED",8000,True,True) if False else DemoFeedbackStore._candidate(
            {"recommended":[result["candidates"][8]],"other_candidates":[]},
            "ACCEPTED",None,True,True)

    with pytest.raises(ReviewConflict):
        DemoFeedbackStore._candidate(result,"SELECTED_OTHER",8000,False)


def test_fewer_than_ten_real_candidates_are_not_fabricated():
    result=build_demo_item(fixture_match(3),12.0)
    assert len(result["candidates"])==3
    assert [c["ld_id"] for c in result["candidates"]]==[8000,8001,8002]


def test_no_recommendation_still_shows_pool_to_investigate():
    m=fixture_match(4)
    m.status="NOT_FOUND"
    m.selected=[]
    m.ld_product=None
    result=build_demo_item(m,12.0)
    assert result["recommended"]==[]
    assert len(result["candidates"])==4
    assert len(result["other_candidates"])==4
