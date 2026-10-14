import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from replay_frozen100_api import grade_one


def test_pass_checks_only_id_locally_after_api_response():
    case={"query":"Кран шаровой DN50 PN16","acceptable_ld_ids":[42,43]}
    assert grade_one(case,{"status":"MATCHED","recommended":[{"ld_id":43}],"metrics":{"latency_ms":3}})["verdict"]=="PASS"
    assert grade_one(case,{"status":"MATCHED","recommended":[{"ld_id":99}]})["verdict"]=="FAIL_WRONG_LD"
    assert grade_one(case,{"status":"NOT_FOUND","recommended":[]})["verdict"]=="FAIL_NOT_FOUND"
    assert grade_one(case,{"status":"ERROR","recommended":[]})["verdict"]=="FAIL_PIPELINE"
