from experiment.decompose.schema import (
    Coverage,
    DecomposeResult,
    GroupDecomposition,
    norm_ten,
    result_to_json,
    validate_criterion,
)


def test_norm_ten_handles_d_and_diacritics():
    assert norm_ten("Đơn dự thầu") == norm_ten("don du thau")


def test_summary_counts():
    g1 = GroupDecomposition(
        group="hop_le", muc="Mục 1",
        criteria=[{"ten": "a"}, {"ten": "b"}],
        needs_review=[{"ten": "a", "ly_do": "x"}],
    )
    g2 = GroupDecomposition(group="tai_chinh", muc="Mục 4", criteria=[{"ten": "c"}])
    r = DecomposeResult(doc="E-HSMT", groups=[g1, g2])
    assert r.summary == {"n_groups": 2, "n_criteria": 3, "n_needs_review": 1}


def test_result_to_json_shape():
    g = GroupDecomposition(group="hop_le", muc="Mục 1", coverage=Coverage(listed_n=1, final_n=2))
    d = result_to_json(DecomposeResult(doc="E-HSMT", groups=[g]))
    assert d["doc"] == "E-HSMT"
    assert d["groups"][0]["coverage"]["final_n"] == 2
    assert d["summary"]["n_groups"] == 1


def test_validate_criterion_shape():
    """validate_criterion chuẩn hoá output phẳng: noi_dung_can_kiem_tra + defaults, no-fab giữ nguyên."""
    crit = {
        "nhom": "hop_le", "ten": "Bảo đảm dự thầu",
        "yeu_cau_goc": "Giá trị, hiệu lực theo HSMT",
        "hsdt_can_kiem_tra": ["Thư bảo lãnh"], "tien_quyet": True,
        "noi_dung_can_kiem_tra": [
            {"ten": "Giá trị bảo lãnh", "gia_tri": "6.100.000 VNĐ", "nguon": "hsmt",
             "kieu_check": "đối chiếu"},
            {"ten": "Thời gian hiệu lực", "nguon": "hsmt"},  # thiếu field -> default
        ],
        "field_la": "bị bỏ",  # extra="ignore"
    }
    out = validate_criterion(crit)
    assert out["tien_quyet"] is True
    assert out["hsdt_can_kiem_tra"] == ["Thư bảo lãnh"]
    assert out["noi_dung_can_kiem_tra"][0]["gia_tri"] == "6.100.000 VNĐ"
    assert out["noi_dung_can_kiem_tra"][1]["gia_tri"] == ""  # default
    assert out["noi_dung_can_kiem_tra"][1]["can_review"] is False
    assert "field_la" not in out
