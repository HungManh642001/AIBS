import pytest
from services.evaluation import legality
from services import ai_client


@pytest.fixture(autouse=True)
def force_mock(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)


CRITERIA = [
    {"nhom": "hop_le", "ten": "Bảo đảm dự thầu", "required_artifacts": ["bao_dam_du_thau"],
     "sub_checks": [
         {"ten": "Có bảo đảm", "check_type": "presence", "thong_so": {}, "required_artifact": "bao_dam_du_thau", "blocking": True},
         {"ten": "Giá trị ≥ ngưỡng", "check_type": "value_threshold", "thong_so": {"gia_tri_so": 150000000}, "required_artifact": "bao_dam_du_thau", "blocking": True},
     ]},
    {"nhom": "ky_thuat", "ten": "Bỏ qua", "required_artifacts": [], "sub_checks": []},
]


@pytest.mark.asyncio
async def test_routed_only_hop_le_and_pass():
    amap = {"bao_dam_du_thau": "Thư bảo lãnh giá trị 200.000.000 đồng"}
    res = await legality.evaluate_legality_routed(CRITERIA, amap)
    assert len(res) == 1 and res[0]["criteria_ten"] == "Bảo đảm dự thầu"
    assert res[0]["result"] == "PASS"
    assert len(res[0]["sub_results"]) == 2


@pytest.mark.asyncio
async def test_routed_missing_artifact_fails():
    res = await legality.evaluate_legality_routed(CRITERIA, {})
    assert res[0]["result"] == "FAIL"


def test_compute_completeness():
    out = legality.compute_completeness(CRITERIA, present_artifacts={"bao_dam_du_thau"})
    assert out["required"] == ["bao_dam_du_thau"]
    assert out["missing"] == [] and out["percent"] == 100.0


@pytest.mark.asyncio
async def test_routed_passes_max_page(monkeypatch):
    seen = {}

    async def fake_eval(criterion, amap, max_page=0):
        seen["max_page"] = max_page
        return []

    from services.evaluation import legality as L
    monkeypatch.setattr(L, "evaluate_criterion", fake_eval)
    await L.evaluate_legality_routed(
        [{"nhom": "hop_le", "ten": "X", "sub_checks": []}], {}, max_page=12)
    assert seen["max_page"] == 12
