import pytest
from services import extraction, ai_client


@pytest.fixture(autouse=True)
def force_mock(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)


@pytest.mark.asyncio
async def test_extract_rubric_mock_shortcircuits():
    sections = {"tcdg": {"located": True, "pages": [{"page": 3, "text": "Tiêu chuẩn đánh giá"}]},
                "bds": {"located": True, "pages": [{"page": 1, "text": "Giá trị bảo đảm: 150 triệu"}]}}
    out = await extraction.extract_rubric(sections)
    assert out.status == "ok"
    crit = out.data["criteria"]
    bdt = next(c for c in crit if c["ten"] == "Bảo đảm dự thầu")
    assert bdt["required_artifacts"] == ["bao_dam_du_thau"]


@pytest.mark.asyncio
async def test_two_step_runs_in_real_mode(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)

    async def fake_list(tcdg_pages):
        return ai_client.AiOutcome("ok", {"criteria": [
            {"nhom": "hop_le", "ten": "Đơn dự thầu", "required_artifacts": ["don_du_thau"]}]}, "qwen3-27b")

    async def fake_detail(crit, tcdg_chunk, bds_pages):
        return ai_client.AiOutcome("ok", {
            "nhom": "hop_le", "ten": crit["ten"], "required_artifacts": crit["required_artifacts"],
            "sub_checks": [{"ten": "Có đơn", "check_type": "presence",
                            "required_artifact": "don_du_thau", "blocking": True}]}, "qwen3-27b")

    monkeypatch.setattr(extraction, "_list_criteria", fake_list)
    monkeypatch.setattr(extraction, "_detail_criterion", fake_detail)
    sections = {"tcdg": {"located": True, "pages": [{"page": 3, "text": "TCĐG"}]},
                "bds": {"located": True, "pages": []}}
    out = await extraction.extract_rubric(sections)
    assert out.status == "ok"
    assert out.data["criteria"][0]["sub_checks"][0]["check_type"] == "presence"


@pytest.mark.asyncio
async def test_list_step_error_propagates(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)

    async def fake_list(tcdg_pages):
        return ai_client.AiOutcome("error", None, "qwen3-27b", "boom")

    monkeypatch.setattr(extraction, "_list_criteria", fake_list)
    sections = {"tcdg": {"located": True, "pages": [{"page": 3, "text": "TCĐG"}]},
                "bds": {"located": True, "pages": []}}
    out = await extraction.extract_rubric(sections)
    assert out.status == "error"
