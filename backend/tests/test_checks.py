from services.evaluation.checks import run_deterministic_check


def test_presence_pass_and_fail():
    assert run_deterministic_check("presence", "có nội dung", {})["result"] == "PASS"
    assert run_deterministic_check("presence", "   ", {})["result"] == "FAIL"


def test_value_threshold_pass():
    r = run_deterministic_check("value_threshold", "Giá trị bảo đảm 200.000.000 đồng", {"gia_tri_so": 150000000})
    assert r["result"] == "PASS"


def test_value_threshold_fail():
    r = run_deterministic_check("value_threshold", "Giá trị bảo đảm 100.000.000 đồng", {"gia_tri_so": 150000000})
    assert r["result"] == "FAIL"


def test_value_threshold_none_when_no_number():
    assert run_deterministic_check("value_threshold", "không có số", {"gia_tri_so": 150000000}) is None


def test_date_validity_pass_and_fail():
    assert run_deterministic_check("date_validity", "hiệu lực 150 ngày", {"so_ngay": 120})["result"] == "PASS"
    assert run_deterministic_check("date_validity", "hiệu lực 90 ngày", {"so_ngay": 120})["result"] == "FAIL"


def test_unsupported_type_returns_none():
    assert run_deterministic_check("semantic_match", "x", {}) is None
