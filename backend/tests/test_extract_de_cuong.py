import pytest
from services import extraction, ai_client


@pytest.fixture(autouse=True)
def force_mock(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)


@pytest.mark.asyncio
async def test_extract_de_cuong_shape():
    sections = {"tcdg": [{"page": 3, "text": "Tiêu chuẩn đánh giá"}],
                "bds": [{"page": 1, "text": "Giá trị bảo đảm: 150 triệu"}]}
    crit = await extraction.extract_de_cuong(sections)
    bdt = next(c for c in crit if c["ten"] == "Bảo đảm dự thầu")
    assert bdt["required_artifacts"] == ["bao_dam_du_thau"]
    sc = {s["check_type"]: s for s in bdt["sub_checks"]}
    assert sc["value_threshold"]["thong_so"]["gia_tri_so"] == 150000000
    assert sc["value_threshold"]["thong_so"]["can_review"] is False
    assert all("required_artifact" in s and "blocking" in s for s in bdt["sub_checks"])
