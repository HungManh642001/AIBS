import pytest
from services import artifact_classify, ai_client


@pytest.fixture(autouse=True)
def force_mock(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)


@pytest.mark.asyncio
async def test_validate_match_true_for_correct_file():
    pages = [{"page": 1, "text": "THƯ BẢO LÃNH dự thầu của ngân hàng ABC"}]
    out = await artifact_classify.validate_artifact(pages, "bao_dam_du_thau")
    assert out["match"] is True


@pytest.mark.asyncio
async def test_validate_match_false_for_wrong_file():
    pages = [{"page": 1, "text": "Đây là báo cáo tài chính năm 2025"}]
    out = await artifact_classify.validate_artifact(pages, "bao_dam_du_thau")
    assert out["match"] is False and out["suggested_type"] == "bao_cao_tai_chinh"
