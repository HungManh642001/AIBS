import pytest
from services.evaluation import base
from services import ai_client


@pytest.fixture(autouse=True)
def force_mock(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)


CRIT = {
    "ten": "Bảo đảm dự thầu", "required_artifacts": ["bao_dam_du_thau"],
    "sub_checks": [
        {"ten": "Có bảo đảm dự thầu", "check_type": "presence", "thong_so": {}, "required_artifact": "bao_dam_du_thau", "blocking": True},
        {"ten": "Giá trị ≥ ngưỡng", "check_type": "value_threshold", "thong_so": {"gia_tri_so": 150000000}, "required_artifact": "bao_dam_du_thau", "blocking": True},
    ],
}


@pytest.mark.asyncio
async def test_missing_artifact_fails_without_ai():
    subs = await base.evaluate_criterion(CRIT, {})  # không có file loại bao_dam_du_thau
    assert all(s["result"] == "FAIL" for s in subs)
    assert "Thiếu hồ sơ" in subs[0]["evidence"]


@pytest.mark.asyncio
async def test_deterministic_value_threshold_used():
    content = {"bao_dam_du_thau": "Thư bảo lãnh giá trị 200.000.000 đồng"}
    subs = await base.evaluate_criterion(CRIT, content)
    vt = next(s for s in subs if s["sub_check_ten"] == "Giá trị ≥ ngưỡng")
    assert vt["result"] == "PASS" and "200" in vt["evidence"]


def test_aggregate_fail_when_blocking_fail():
    subs = [{"sub_check_ten": "Có bảo đảm dự thầu", "result": "FAIL", "evidence": "", "page_ref": [], "nguon_file": "", "ai_model": ""}]
    agg = base.aggregate_subresults(CRIT, subs)
    assert agg["result"] == "FAIL"


def test_aggregate_partial_when_nonblocking_fail():
    crit = {"sub_checks": [
        {"ten": "A", "blocking": True}, {"ten": "B", "blocking": False}]}
    subs = [
        {"sub_check_ten": "A", "result": "PASS", "evidence": "", "page_ref": [], "nguon_file": "", "ai_model": ""},
        {"sub_check_ten": "B", "result": "FAIL", "evidence": "", "page_ref": [], "nguon_file": "", "ai_model": ""},
    ]
    agg = base.aggregate_subresults(crit, subs)
    assert agg["result"] == "PARTIAL"


def test_aggregate_pass_when_all_pass():
    subs = [{"sub_check_ten": s["ten"], "result": "PASS", "evidence": "", "page_ref": [], "nguon_file": "", "ai_model": ""}
            for s in CRIT["sub_checks"]]
    agg = base.aggregate_subresults(CRIT, subs)
    assert agg["result"] == "PASS" and agg["score"] == 100.0


@pytest.mark.asyncio
async def test_ai_error_becomes_error_result(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)

    async def boom(*a, **k):
        return ai_client.AiOutcome("error", None, "qwen3-27b", "timeout")

    monkeypatch.setattr(base, "ai_call", boom)
    crit = {"ten": "X", "required_artifacts": ["don_du_thau"], "sub_checks": [
        {"ten": "Suy xét nội dung", "check_type": "semantic_match", "thong_so": {},
         "required_artifact": "don_du_thau", "blocking": True}]}
    subs = await base.evaluate_criterion(crit, {"don_du_thau": "nội dung đơn"})
    assert subs[0]["result"] == "ERROR"
    assert "timeout" in subs[0]["evidence"]


@pytest.mark.asyncio
async def test_artifact_outside_catalog_is_error_not_fail():
    crit = {"ten": "X", "required_artifacts": ["khong_ton_tai"], "sub_checks": [
        {"ten": "Kiểm tra", "check_type": "presence", "thong_so": {},
         "required_artifact": "khong_ton_tai", "blocking": True}]}
    subs = await base.evaluate_criterion(crit, {"khong_ton_tai": "abc"})
    assert subs[0]["result"] == "ERROR"
    assert "ngoài danh mục" in subs[0]["evidence"]


def test_aggregate_error_takes_precedence():
    crit = {"sub_checks": [{"ten": "A", "blocking": True}, {"ten": "B", "blocking": True}]}
    subs = [
        {"sub_check_ten": "A", "result": "PASS", "evidence": "", "page_ref": [], "nguon_file": "", "ai_model": ""},
        {"sub_check_ten": "B", "result": "ERROR", "evidence": "", "page_ref": [], "nguon_file": "", "ai_model": ""},
    ]
    assert base.aggregate_subresults(crit, subs)["result"] == "ERROR"
