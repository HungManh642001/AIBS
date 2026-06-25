import pytest
from services.evaluation import capacity, technical
from services import ai_client


@pytest.fixture(autouse=True)
def force_mock(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)


CRITERIA = [
    {"nhom": "nang_luc", "ten": "Doanh thu 3 năm", "yeu_cau": ">=1.5x", "kieu": "pass_fail"},
    {"nhom": "ky_thuat", "ten": "Thông số kỹ thuật", "yeu_cau": ">=90%", "kieu": "score", "trong_so": 60},
]
PAGES = [{"page": 4, "text": "Doanh thu 3 năm 1.8x; đáp ứng 88% thông số"}]


@pytest.mark.asyncio
async def test_capacity_only_nang_luc():
    res = await capacity.evaluate_capacity(CRITERIA, PAGES)
    assert len(res) == 1
    assert res[0]["criteria_ten"] == "Doanh thu 3 năm"


@pytest.mark.asyncio
async def test_technical_only_ky_thuat_has_score():
    res = await technical.evaluate_technical(CRITERIA, PAGES)
    assert len(res) == 1
    assert 0 <= res[0]["score"] <= 100
