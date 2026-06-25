from decimal import Decimal
from services.evaluation import financial


def test_recalc_detects_arithmetic_error():
    rows = [
        [1, "Máy chủ", 100, 2, 250],   # sai: đúng phải 200
        [2, "Switch", 50, 3, 150],     # đúng
    ]
    res = financial.recalc_price_table(rows)
    assert res["tong_gia"] == Decimal("350")
    assert len(res["errors"]) == 1
    assert res["errors"][0]["stt"] == 1
    assert res["errors"][0]["gia_tri_dung"] == Decimal("200")
    assert res["evaluated_price"] == Decimal("350")


def test_recalc_no_error_when_correct():
    rows = [[1, "A", 10, 2, 20]]
    res = financial.recalc_price_table(rows)
    assert res["errors"] == []
    assert res["tong_gia"] == Decimal("20")
