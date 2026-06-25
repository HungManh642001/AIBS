import pytest
from decimal import Decimal
from services.evaluation import orchestrator
from services import ai_client


@pytest.fixture(autouse=True)
def force_mock(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)


CRITERIA = [
    {"nhom": "hop_le", "ten": "Đơn dự thầu", "kieu": "pass_fail"},
    {"nhom": "nang_luc", "ten": "Doanh thu", "kieu": "pass_fail"},
    {"nhom": "ky_thuat", "ten": "Thông số", "kieu": "score", "trong_so": 100},
]
HSDT = [{"page": 1, "text": "nội dung"}]
PRICE = [{"page": 1, "text": "1\tMáy\t100\t2\t200"}]


@pytest.mark.asyncio
async def test_evaluate_vendor_shapes():
    ev = await orchestrator.evaluate_vendor(CRITERIA, HSDT, PRICE)
    assert ev["passed_legality"] is True
    assert 0 <= ev["technical_score"] <= 100
    assert ev["financial"]["evaluated_price"] == Decimal("200")


def test_rank_orders_by_evaluated_price():
    evals = {
        1: {"passed_legality": True, "technical_score": 80,
            "financial": {"evaluated_price": Decimal("300")}},
        2: {"passed_legality": True, "technical_score": 70,
            "financial": {"evaluated_price": Decimal("200")}},
        3: {"passed_legality": False, "technical_score": 0,
            "financial": {"evaluated_price": Decimal("100")}},
    }
    ranked = orchestrator.rank_vendors(evals)
    eligible = [r for r in ranked if r["eligible"]]
    assert eligible[0]["vendor_id"] == 2 and eligible[0]["rank"] == 1
    assert eligible[1]["vendor_id"] == 1 and eligible[1]["rank"] == 2
    assert any(r["vendor_id"] == 3 and r["rank"] is None for r in ranked)
