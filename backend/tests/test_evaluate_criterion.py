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
    subs = [{"sub_check_ten": "Có", "result": "FAIL", "evidence": "", "page_ref": [], "nguon_file": "", "ai_model": ""}]
    agg = base.aggregate_subresults(CRIT, subs)
    assert agg["result"] == "FAIL"


def test_aggregate_pass_when_all_pass():
    subs = [{"sub_check_ten": s["ten"], "result": "PASS", "evidence": "", "page_ref": [], "nguon_file": "", "ai_model": ""}
            for s in CRIT["sub_checks"]]
    agg = base.aggregate_subresults(CRIT, subs)
    assert agg["result"] == "PASS" and agg["score"] == 100.0
