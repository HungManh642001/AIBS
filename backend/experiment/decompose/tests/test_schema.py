from experiment.decompose.schema import (
    Coverage,
    DecomposeResult,
    GroupDecomposition,
    norm_ten,
    result_to_json,
    validate_criteria,
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


def test_validate_criteria_keeps_extra_flags():
    crit = {
        "nhom": "hop_le", "ten": "Bảo đảm dự thầu", "kieu": "pass_fail",
        "sub_checks": [{"ten": "có bảo đảm", "check_type": "presence"}],
        "can_review": True, "loi_ai": "proxy down",  # field thêm phải GIỮ lại
    }
    out = validate_criteria([crit])
    assert out[0]["can_review"] is True
    assert out[0]["loi_ai"] == "proxy down"
    assert out[0]["sub_checks"][0]["ten"] == "có bảo đảm"
