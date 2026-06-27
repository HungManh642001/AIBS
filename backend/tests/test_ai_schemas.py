import pytest
from services import ai_schemas


def test_eval_verdict_ok():
    out = ai_schemas.validate_eval_verdict(
        {"evidence": "có chữ ký", "result": "PASS", "score": 90, "page_ref": [1]})
    assert out["result"] == "PASS" and out["score"] == 90


def test_eval_verdict_missing_required_raises():
    with pytest.raises(Exception):
        ai_schemas.validate_eval_verdict({"score": 90})  # thiếu evidence + result


def test_sub_verdict_ok():
    out = ai_schemas.validate_sub_verdict({"evidence": "x", "result": "FAIL"})
    assert out["result"] == "FAIL" and out["page_ref"] == []


def test_criteria_list_ok():
    out = ai_schemas.validate_criteria_list(
        {"criteria": [{"nhom": "hop_le", "ten": "Đơn dự thầu", "required_artifacts": ["don_du_thau"]}]})
    assert out["criteria"][0]["ten"] == "Đơn dự thầu"


def test_criteria_list_item_without_ten_raises():
    with pytest.raises(Exception):
        ai_schemas.validate_criteria_list({"criteria": [{"nhom": "hop_le"}]})


def test_criterion_detail_ok():
    out = ai_schemas.validate_criterion_detail({
        "ten": "Bảo đảm dự thầu",
        "sub_checks": [{"ten": "Có bảo đảm", "check_type": "presence",
                        "required_artifact": "bao_dam_du_thau", "blocking": True}]})
    assert out["sub_checks"][0]["blocking"] is True
