import pytest
from services import extraction
from services import ai_client


@pytest.fixture(autouse=True)
def force_mock(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)


@pytest.mark.asyncio
async def test_extract_criteria_groups():
    pages = [{"page": 1, "text": "Tiêu chí đánh giá..."}]
    criteria = await extraction.extract_criteria(pages)
    nhoms = {c["nhom"] for c in criteria}
    assert {"hop_le", "nang_luc", "ky_thuat", "tai_chinh"} <= nhoms
    assert all("ten" in c for c in criteria)


@pytest.mark.asyncio
async def test_map_hsdt_returns_evidence():
    criteria = [{"ten": "Đơn dự thầu hợp lệ"}]
    pages = [{"page": 1, "text": "Đơn dự thầu..."}]
    mappings = await extraction.map_hsdt(criteria, pages)
    assert mappings[0]["page_ref"]
