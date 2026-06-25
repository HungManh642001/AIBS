import pytest
from services.evaluation import legality
from services import ai_client


@pytest.fixture(autouse=True)
def force_mock(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)


@pytest.mark.asyncio
async def test_legality_produces_result_with_evidence():
    criteria = [
        {"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ", "yeu_cau": "Có chữ ký", "kieu": "pass_fail"},
        {"nhom": "ky_thuat", "ten": "Bỏ qua", "yeu_cau": "", "kieu": "score"},
    ]
    pages = [{"page": 1, "text": "Đơn dự thầu ký hợp lệ"}]
    results = await legality.evaluate_legality(criteria, pages)
    assert len(results) == 1  # chỉ tiêu chí hop_le
    r = results[0]
    assert r["result"] in {"PASS", "FAIL", "PARTIAL"}
    assert r["evidence"]
    assert isinstance(r["page_ref"], list)
