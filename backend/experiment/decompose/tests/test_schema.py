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
        "hsdt_can_kiem_tra": ["bao_lanh_du_thau"],
        "noi_dung_can_kiem_tra": [
            {"noi_dung_kiem_tra": "Giá trị bảo lãnh", "hsdt_kiem_tra": "bao_lanh_du_thau",
             "yeu_cau": "Thỏa mãn giá trị bảo lãnh", "can_lam_ro": "Giá trị bảo lãnh",
             "can_tra_cuu": True},
            {"noi_dung_kiem_tra": "Thời gian hiệu lực", "can_tra_cuu": True},  # thiếu field -> default
        ],
        "field_la": "bị bỏ",  # extra="ignore"
    }
    out = validate_criterion(crit)
    assert out["hsdt_can_kiem_tra"] == ["bao_lanh_du_thau"]
    nd0 = out["noi_dung_can_kiem_tra"][0]
    assert nd0["yeu_cau"] == "Thỏa mãn giá trị bảo lãnh"
    assert nd0["can_lam_ro"] == "Giá trị bảo lãnh"
    assert nd0["thong_tin_bo_sung"] == "" and nd0["nguon"] == ""  # step 3 mới điền
    assert out["noi_dung_can_kiem_tra"][1]["thong_tin_bo_sung"] == ""  # default
    assert out["noi_dung_can_kiem_tra"][1]["can_review"] is False
    assert "field_la" not in out


def test_tieu_chi_khong_con_tien_quyet():
    """Decompose không bóc 'tiên quyết' từ HSMT nữa — hệ thống không dùng thuộc tính này."""
    from experiment.decompose.schema import CriterionModel

    assert "tien_quyet" not in CriterionModel.model_fields


# ---- mệnh đề "hoặc": prompt phải dạy GỘP, không tách (ca thật gói 54 nd#156/#157) ----
def test_sys_struct_cam_tach_menh_de_hoac():
    """Hai vế nối 'hoặc' là hai cách thoả CÙNG một yêu cầu; tách ra biến HOẶC thành VÀ."""
    from experiment.decompose.prompts import SYS_STRUCT

    s = SYS_STRUCT.lower()
    assert "hoặc" in s and "không được tách" in s
    assert "thoả một" in s or "thoả cùng một" in s or "một vế" in s


def test_vi_du_3_giu_du_ca_hai_ve_cua_hoac():
    """Ví dụ 3 từng chỉ nêu vế 'thành viên đứng đầu ký' -> chính nó dạy model bỏ vế kia."""
    from experiment.decompose.prompts import struct_prompt

    p = struct_prompt({"ten": "X", "nhom": "hop_le", "yeu_cau_goc": "", "hsdt_can_kiem_tra": []})
    i = p.find("VÍ DỤ 3")
    khoi = p[i:p.find("DANH MỤC ĐẠI LƯỢNG", i)]
    assert "TỪNG thành viên" in khoi and "đứng đầu" in khoi
    assert "HOẶC" in khoi and "MỘT trong hai" in khoi


def test_sys_eval_biet_hoac_chi_can_thoa_mot():
    """Sửa decompose là vô nghĩa nếu bước chấm vẫn đòi thoả hết các vế."""
    from experiment.evaluate.prompts import SYS_EVAL

    assert "hoặc" in SYS_EVAL.lower()
    assert "MỘT phương án" in SYS_EVAL and "KHÔNG đòi thỏa hết" in SYS_EVAL
