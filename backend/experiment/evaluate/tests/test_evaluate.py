from experiment.evaluate.evaluate import eval_noi_dung, evaluate_criterion
from experiment.evaluate.vision import ScriptedVision
from experiment.evaluate.schema import PageRecord, KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_THIEU


def _page(loai, text, image=b"\x89PNG", co_chu_ky=False):
    return PageRecord(file="f.pdf", trang=1, loai_ho_so=loai, text=text, co_chu_ky=co_chu_ky, image=image)


def _nd(noi_dung, hsdt):
    return {"noi_dung_kiem_tra": noi_dung, "hsdt_kiem_tra": hsdt, "yeu_cau": "theo HSMT",
            "thong_tin_bo_sung": "6.100.000 VNĐ"}


async def test_eval_noi_dung_missing_doc_is_thieu_ho_so():
    v = await eval_noi_dung(_nd("Giá trị bảo lãnh", "bao_dam_du_thau"),
                            [_page("don_du_thau", "đơn")], ScriptedVision({}))
    assert v.ket_qua == KET_QUA_THIEU     # không có trang bảo đảm dự thầu


async def test_eval_noi_dung_pass_from_text():
    vision = ScriptedVision({"[EV:Giá trị bảo lãnh]":
                             {"ket_qua": "đạt", "bang_chung": "6.100.000", "trang": [1], "do_tin": 0.9}})
    v = await eval_noi_dung(_nd("Giá trị bảo lãnh", "bao_dam_du_thau"),
                            [_page("bao_dam_du_thau", "bảo lãnh 6.100.000 VNĐ")], vision)
    assert v.ket_qua == KET_QUA_DAT and v.trang == [1]
    assert v.thong_tin_bo_sung == "6.100.000 VNĐ"   # chuẩn HSMT lưu vào verdict để audit
    assert vision.calls[-1][1] == 0                 # eval THUẦN TEXT -> KHÔNG bao giờ đính ảnh


async def test_eval_signature_check_from_ingest_text():
    # Chữ ký/dấu đã được ingest mô tả trong text + cờ -> eval kết luận trên text, KHÔNG cần ảnh.
    vision = ScriptedVision({"[EV:Chữ ký & đóng dấu]":
                             {"ket_qua": "đạt", "bang_chung": "có chữ ký và con dấu đỏ", "trang": [1]}})
    v = await eval_noi_dung(_nd("Chữ ký & đóng dấu", "bao_dam_du_thau"),
                            [_page("bao_dam_du_thau", "Thư bảo lãnh (có chữ ký; có đóng dấu)", co_chu_ky=True)],
                            vision)
    assert v.ket_qua == KET_QUA_DAT
    assert vision.calls[-1][1] == 0                 # không đính ảnh


async def test_criterion_rollup_khong_dat():
    crit = {"nhom": "hop_le", "ten": "Bảo đảm dự thầu",
            "noi_dung_can_kiem_tra": [_nd("Giá trị bảo lãnh", "bao_dam_du_thau")]}
    vision = ScriptedVision({"[EV:Giá trị bảo lãnh]":
                             {"ket_qua": "không đạt", "bang_chung": "3 triệu < 6.1tr", "trang": [1]}})
    ce = await evaluate_criterion(crit, [_page("bao_dam_du_thau", "bảo lãnh 3.000.000")], vision)
    assert ce.ket_qua == KET_QUA_KHONG


def _crit_na(ten="Đơn dự thầu", nds=None):
    """Tiêu chí có nội dung TTLĐ -> nhà thầu độc lập sẽ gate thành N/A (đường N/A THẬT, 0 call)."""
    return {"nhom": "hop_le", "ten": ten,
            "noi_dung_can_kiem_tra": nds if nds is not None else [_nd("TTLD", "thoa_thuan_lien_danh")]}


async def test_rollup_na_is_neutral():
    """N/A trung tính: [đạt, N/A] -> tiêu chí 'đạt' (N/A không kéo xuống 'cần làm rõ')."""
    from experiment.evaluate.schema import HINH_THUC_DOC_LAP, KET_QUA_KHONG_AP_DUNG

    crit = _crit_na(nds=[_nd("Có đơn dự thầu", "don_du_thau"), _nd("TTLD", "thoa_thuan_lien_danh")])
    vision = ScriptedVision({"[EV:Có đơn dự thầu]": {"ket_qua": "đạt", "bang_chung": "có", "trang": [1]}})
    ce = await evaluate_criterion(crit, [_page("don_du_thau", "đơn")], vision,
                                  profile=_profile(HINH_THUC_DOC_LAP))
    assert [v.ket_qua for v in ce.verdicts] == [KET_QUA_DAT, KET_QUA_KHONG_AP_DUNG]
    assert ce.ket_qua == KET_QUA_DAT


async def test_rollup_all_na_criterion_is_na_not_loai():
    """Toàn bộ verdict N/A -> tiêu chí 'không áp dụng'."""
    from experiment.evaluate.schema import HINH_THUC_DOC_LAP, KET_QUA_KHONG_AP_DUNG

    ce = await evaluate_criterion(_crit_na(ten="Thỏa thuận liên danh"),
                                  [_page("don_du_thau", "đơn")], ScriptedVision({}),
                                  profile=_profile(HINH_THUC_DOC_LAP))
    assert ce.ket_qua == KET_QUA_KHONG_AP_DUNG


async def test_rollup_na_plus_khong_dat_still_loai():
    """N/A KHÔNG che 'không đạt': tiêu chí vẫn ra 'không đạt'."""
    from experiment.evaluate.schema import HINH_THUC_DOC_LAP

    crit = _crit_na(nds=[_nd("Có đơn dự thầu", "don_du_thau"), _nd("TTLD", "thoa_thuan_lien_danh")])
    vision = ScriptedVision({"[EV:Có đơn dự thầu]": {"ket_qua": "không đạt", "bang_chung": "x", "trang": [1]}})
    ce = await evaluate_criterion(crit, [_page("don_du_thau", "đơn")], vision,
                                  profile=_profile(HINH_THUC_DOC_LAP))
    assert ce.ket_qua == KET_QUA_KHONG


async def test_rollup_empty_verdicts_still_soi():
    """Tiêu chí KHÔNG có verdict nào -> 'cần làm rõ' (giữ hành vi cũ, không thành N/A)."""
    from experiment.evaluate.schema import KET_QUA_SOI

    ce = await evaluate_criterion({"nhom": "hop_le", "ten": "X", "noi_dung_can_kiem_tra": []},
                                  [], ScriptedVision({}))
    assert ce.ket_qua == KET_QUA_SOI


def _profile(hinh_thuc, nguon="khai báo", **kw):
    from experiment.evaluate.schema import VendorProfile
    return VendorProfile(hinh_thuc=hinh_thuc, nguon=nguon, **kw)


async def test_gate_lien_danh_doc_lap_is_na_zero_call():
    """Nhà thầu độc lập + hồ sơ CHỈ dành cho liên danh -> N/A TẤT ĐỊNH, 0 call AI."""
    from experiment.evaluate.schema import HINH_THUC_DOC_LAP, KET_QUA_KHONG_AP_DUNG

    v = ScriptedVision({})
    got = await eval_noi_dung(_nd("Thỏa thuận liên danh hợp lệ", "thoa_thuan_lien_danh"),
                              [_page("don_du_thau", "đơn")], v,
                              profile=_profile(HINH_THUC_DOC_LAP, do_tin=1.0))
    assert got.ket_qua == KET_QUA_KHONG_AP_DUNG
    assert v.calls == []
    assert "độc lập" in got.ghi_chu and "khai báo" in got.ghi_chu   # căn cứ hiện rõ để kiểm chứng


async def test_gate_dieu_kien_gia_tri_na_ke_ca_khi_khong_co_profile():
    """Điều kiện theo GIÁ TRỊ không phụ thuộc hình thức -> phải gate cả khi profile=None.

    Prod (services/hsdt_pipeline) có đường KHÔNG truyền profile; nếu gate này đặt sau nhánh
    `profile is None` thì cơ chế chết lặng ở đúng nơi cần nó nhất.
    """
    from experiment.evaluate.schema import KET_QUA_KHONG_AP_DUNG

    nd = _nd("Cam kết bảo đảm dự thầu trong đơn", "don_du_thau")
    nd["dieu_kien_ap_dung"] = {"ket_luan": "khong_ap_dung",
                               "can_cu": "giá trị bảo đảm dự thầu = 939,000,000 — KHÔNG THOẢ < 50 triệu đồng"}
    v = ScriptedVision({})
    got = await eval_noi_dung(nd, [_page("don_du_thau", "đơn")], v, profile=None)

    assert got.ket_qua == KET_QUA_KHONG_AP_DUNG
    assert v.calls == []                       # TẤT ĐỊNH, 0 call AI
    assert "939,000,000" in got.ghi_chu        # căn cứ đi tới báo cáo cho chuyên gia kiểm chứng


async def test_gate_dieu_kien_chua_quyet_duoc_thi_van_cham():
    """FAIL-SAFE: decompose không quyết được (ket_luan='') -> KHÔNG bỏ, chấm bình thường."""
    nd = _nd("Cam kết bảo đảm dự thầu trong đơn", "don_du_thau")
    nd["dieu_kien_ap_dung"] = {"ket_luan": "", "can_cu": "không tra được — vẫn chấm"}
    vision = ScriptedVision({"[EV:Cam kết bảo đảm dự thầu trong đơn]":
                             {"ket_qua": "đạt", "bang_chung": "có cam kết", "trang": [1]}})

    got = await eval_noi_dung(nd, [_page("don_du_thau", "đơn có cam kết")], vision)
    assert got.ket_qua == KET_QUA_DAT


async def test_gate_off_when_hinh_thuc_khong_ro_falls_back_to_thieu():
    """FAIL-SAFE: hình thức không rõ -> KHÔNG gate -> vẫn 'thiếu hồ sơ' như hiện nay."""
    from experiment.evaluate.schema import VendorProfile

    got = await eval_noi_dung(_nd("TTLD hợp lệ", "thoa_thuan_lien_danh"),
                              [_page("don_du_thau", "đơn")], ScriptedVision({}),
                              profile=VendorProfile())
    assert got.ket_qua == KET_QUA_THIEU


async def test_gate_off_for_lien_danh_vendor():
    """Liên danh thiếu thỏa thuận -> 'thiếu hồ sơ' (PHÁT HIỆN THẬT), tuyệt đối KHÔNG N/A."""
    from experiment.evaluate.schema import HINH_THUC_LIEN_DANH

    got = await eval_noi_dung(_nd("TTLD hợp lệ", "thoa_thuan_lien_danh"),
                              [_page("don_du_thau", "đơn")], ScriptedVision({}),
                              profile=_profile(HINH_THUC_LIEN_DANH))
    assert got.ket_qua == KET_QUA_THIEU


async def test_gate_only_hits_thoa_thuan_lien_danh():
    """Độc lập KHÔNG được N/A hồ sơ khác — chỉ hồ sơ riêng của liên danh."""
    from experiment.evaluate.schema import HINH_THUC_DOC_LAP

    got = await eval_noi_dung(_nd("Giá trị bảo lãnh", "bao_dam_du_thau"),
                              [_page("don_du_thau", "đơn")], ScriptedVision({}),
                              profile=_profile(HINH_THUC_DOC_LAP))
    assert got.ket_qua == KET_QUA_THIEU


async def test_gate_matches_via_norm():
    """hsdt_kiem_tra có dấu/hoa vẫn gate được (chuẩn hoá _norm)."""
    from experiment.evaluate.schema import HINH_THUC_DOC_LAP, KET_QUA_KHONG_AP_DUNG

    got = await eval_noi_dung(_nd("TTLD", "Thỏa_Thuận_Liên_Danh"),
                              [_page("don_du_thau", "đơn")], ScriptedVision({}),
                              profile=_profile(HINH_THUC_DOC_LAP))
    assert got.ket_qua == KET_QUA_KHONG_AP_DUNG


async def test_gate_beats_can_review():
    """Gate đứng TRƯỚC can_review: N/A thông tin hơn 'chuẩn HSMT chưa tra được'."""
    from experiment.evaluate.schema import HINH_THUC_DOC_LAP, KET_QUA_KHONG_AP_DUNG

    nd = {"noi_dung_kiem_tra": "TTLD", "hsdt_kiem_tra": "thoa_thuan_lien_danh",
          "yeu_cau": "theo HSMT", "thong_tin_bo_sung": "", "can_review": True}
    got = await eval_noi_dung(nd, [_page("don_du_thau", "đơn")], ScriptedVision({}),
                              profile=_profile(HINH_THUC_DOC_LAP))
    assert got.ket_qua == KET_QUA_KHONG_AP_DUNG


async def test_ai_na_blocked_when_form_unknown():
    """AI trả 'không áp dụng' mà hình thức không rõ -> CODE ép về 'cần làm rõ' (không tin AI)."""
    from experiment.evaluate.schema import KET_QUA_SOI, VendorProfile

    v = ScriptedVision({"[EV:X]": {"ket_qua": "không áp dụng", "bang_chung": "b", "trang": [1]}})
    got = await eval_noi_dung(_nd("X", "don_du_thau"), [_page("don_du_thau", "t")], v,
                              profile=VendorProfile())
    assert got.ket_qua == KET_QUA_SOI


async def test_ai_na_blocked_when_form_is_lien_danh():
    """Liên danh -> N/A vô nghĩa -> ép 'cần làm rõ'."""
    from experiment.evaluate.schema import HINH_THUC_LIEN_DANH, KET_QUA_SOI

    v = ScriptedVision({"[EV:X]": {"ket_qua": "không áp dụng", "bang_chung": "b"}})
    got = await eval_noi_dung(_nd("X", "don_du_thau"), [_page("don_du_thau", "t")], v,
                              profile=_profile(HINH_THUC_LIEN_DANH))
    assert got.ket_qua == KET_QUA_SOI


async def test_ai_na_accepted_when_doc_lap():
    """Độc lập + yêu cầu chỉ dành cho liên danh -> AI được trả N/A."""
    from experiment.evaluate.schema import HINH_THUC_DOC_LAP, KET_QUA_KHONG_AP_DUNG

    v = ScriptedVision({"[EV:X]": {"ket_qua": "không áp dụng", "bang_chung": "",
                                   "ghi_chu": "yêu cầu chỉ áp dụng cho liên danh"}})
    got = await eval_noi_dung(_nd("X", "don_du_thau"), [_page("don_du_thau", "t")], v,
                              profile=_profile(HINH_THUC_DOC_LAP))
    assert got.ket_qua == KET_QUA_KHONG_AP_DUNG
    assert got.ghi_chu == "yêu cầu chỉ áp dụng cho liên danh"


async def test_ai_na_without_ghi_chu_gets_code_generated_basis():
    """AI trả N/A nhưng bỏ trống ghi_chu -> code điền căn cứ ĐÃ BIẾT (không bịa lý do)."""
    from experiment.evaluate.schema import HINH_THUC_DOC_LAP, KET_QUA_KHONG_AP_DUNG

    v = ScriptedVision({"[EV:X]": {"ket_qua": "không áp dụng", "ghi_chu": ""}})
    got = await eval_noi_dung(_nd("X", "don_du_thau"), [_page("don_du_thau", "t")], v,
                              profile=_profile(HINH_THUC_DOC_LAP))
    assert got.ket_qua == KET_QUA_KHONG_AP_DUNG
    assert "độc lập" in got.ghi_chu and "khai báo" in got.ghi_chu


async def test_eval_prompt_gets_vendor_form_through_criterion():
    """evaluate_criterion truyền profile/vendor_ctx xuống tận prompt của mỗi nội dung."""
    from experiment.evaluate.schema import HINH_THUC_DOC_LAP, VendorContext

    crit = {"nhom": "hop_le", "ten": "Đơn dự thầu",
            "noi_dung_can_kiem_tra": [_nd("Có đơn dự thầu", "don_du_thau")]}
    v = ScriptedVision({"[EV:Có đơn dự thầu]": {"ket_qua": "đạt", "bang_chung": "có", "trang": [1]}})
    await evaluate_criterion(crit, [_page("don_du_thau", "đơn")], v,
                             vendor_ctx=VendorContext(ten="Công ty ABC"),
                             profile=_profile(HINH_THUC_DOC_LAP))
    assert "Công ty ABC" in v.calls[-1][0] and "độc lập" in v.calls[-1][0]


async def test_criterion_passes_yeu_cau_goc_and_siblings_to_each_need():
    """1 yeu_cau_goc -> N yeu_cau: mỗi call thấy nguyên văn gốc + đúng tên anh em (không có tên nó)."""
    crit = {"nhom": "hop_le", "ten": "Bảo đảm dự thầu",
            "yeu_cau_goc": "Nộp bảo đảm dự thầu 6.100.000 VNĐ, hiệu lực 120 ngày",
            "noi_dung_can_kiem_tra": [_nd("Giá trị bảo lãnh", "bao_dam_du_thau"),
                                      _nd("Thời gian hiệu lực", "bao_dam_du_thau"),
                                      _nd("Đơn vị thụ hưởng", "bao_dam_du_thau")]}
    vision = ScriptedVision({"[EV:Giá trị bảo lãnh]": {"ket_qua": "đạt", "bang_chung": "6.1tr"},
                             "[EV:Thời gian hiệu lực]": {"ket_qua": "đạt", "bang_chung": "120n"},
                             "[EV:Đơn vị thụ hưởng]": {"ket_qua": "đạt", "bang_chung": "CĐT"}})
    await evaluate_criterion(crit, [_page("bao_dam_du_thau", "thư bảo lãnh")], vision)

    assert len(vision.calls) == 3
    for hay, _ in vision.calls:
        assert "Nộp bảo đảm dự thầu 6.100.000 VNĐ, hiệu lực 120 ngày" in hay   # gốc xuống mọi need
    dau = vision.calls[0][0]        # need "Giá trị bảo lãnh" -> anh em là 2 need còn lại
    assert "Thời gian hiệu lực" in dau and "Đơn vị thụ hưởng" in dau


async def test_verdict_carries_nguon_hsmt_on_every_path():
    """Mã điều khoản HSMT theo verdict trên MỌI đường — chuỗi audit không được đứt."""
    from experiment.evaluate.schema import HINH_THUC_DOC_LAP

    nd_thieu = dict(_nd("Giá trị bảo lãnh", "bao_dam_du_thau"), nguon="E-BDL 18.1")
    v = await eval_noi_dung(nd_thieu, [], ScriptedVision({}))
    assert v.ket_qua == KET_QUA_THIEU and v.nguon_hsmt == "E-BDL 18.1"

    nd_review = {"noi_dung_kiem_tra": "X", "hsdt_kiem_tra": "don_du_thau", "yeu_cau": "y",
                 "thong_tin_bo_sung": "", "can_review": True, "nguon": "E-CDNT 1.1"}
    v2 = await eval_noi_dung(nd_review, [_page("don_du_thau", "đơn")], ScriptedVision({}))
    assert v2.nguon_hsmt == "E-CDNT 1.1"

    nd_na = dict(_nd("TTLD", "thoa_thuan_lien_danh"), nguon="E-BDL 2.3")
    v3 = await eval_noi_dung(nd_na, [_page("don_du_thau", "đơn")], ScriptedVision({}),
                             profile=_profile(HINH_THUC_DOC_LAP))
    assert v3.nguon_hsmt == "E-BDL 2.3"

    vision = ScriptedVision({"[EV:Giá trị bảo lãnh]": {"ket_qua": "đạt", "bang_chung": "6tr"}})
    v4 = await eval_noi_dung(nd_thieu, [_page("bao_dam_du_thau", "6tr")], vision)
    assert v4.ket_qua == KET_QUA_DAT and v4.nguon_hsmt == "E-BDL 18.1"

    assert (await eval_noi_dung(_nd("X", "don_du_thau"), [], ScriptedVision({}))).nguon_hsmt == ""


async def test_criterion_carries_yeu_cau_goc():
    crit = {"nhom": "hop_le", "ten": "X", "yeu_cau_goc": "Nhà thầu phải nộp bảo đảm 6.100.000 VNĐ",
            "noi_dung_can_kiem_tra": []}
    ce = await evaluate_criterion(crit, [], ScriptedVision({}))
    assert ce.yeu_cau_goc == "Nhà thầu phải nộp bảo đảm 6.100.000 VNĐ"
    assert (await evaluate_criterion({"ten": "Y"}, [], ScriptedVision({}))).yeu_cau_goc == ""


async def test_eval_can_review_short_circuits_no_llm():
    """Need decompose cờ can_review (chuẩn HSMT tra không ra) -> 'cần làm rõ' TẤT ĐỊNH, 0 call."""
    from experiment.evaluate.schema import KET_QUA_SOI

    vision = ScriptedVision({})
    nd = {"noi_dung_kiem_tra": "Giá trị bảo lãnh", "hsdt_kiem_tra": "bao_dam_du_thau",
          "yeu_cau": "theo HSMT", "thong_tin_bo_sung": "", "can_review": True}
    v = await eval_noi_dung(nd, [_page("bao_dam_du_thau", "bảo lãnh 6tr")], vision)
    assert v.ket_qua == KET_QUA_SOI and "chuẩn HSMT" in v.ghi_chu
    assert vision.calls == []                       # KHÔNG gọi LLM khi không có chuẩn (no-fab)

    # can_review nhưng chuẩn ĐÃ có (dữ liệu cũ lẫn lộn) -> vẫn đánh giá bình thường
    vision2 = ScriptedVision({"[EV:Giá trị bảo lãnh]": {"ket_qua": "đạt", "bang_chung": "6tr", "trang": [1]}})
    nd2 = dict(nd, thong_tin_bo_sung="6.100.000 VNĐ")
    v2 = await eval_noi_dung(nd2, [_page("bao_dam_du_thau", "bảo lãnh 6tr")], vision2)
    assert v2.ket_qua == KET_QUA_DAT


def _wf(text="1|Cty ABC|1.2 tỷ\n2|Cty DEF|1.15 tỷ"):
    return PageRecord(file="webform.pdf", trang=1, loai_ho_so="webform", text=text)


async def test_shared_doc_without_vendor_ctx_is_soi_no_call():
    """Tài liệu DÙNG CHUNG mà không có ngữ cảnh nhà thầu -> thà thiếu căn cứ còn hơn chấm nhầm dòng."""
    from experiment.evaluate.schema import KET_QUA_SOI

    v = ScriptedVision({"[EV:Giá webform]": {"ket_qua": "đạt", "bang_chung": "x"}})
    got = await eval_noi_dung(_nd("Giá webform", "webform"), [_wf()], v)
    assert got.ket_qua == KET_QUA_SOI and v.calls == []
    assert "dùng chung" in got.ghi_chu and "thiếu ngữ cảnh" in got.ghi_chu


async def test_shared_doc_page_without_vendor_is_dropped():
    """Trang webform KHÔNG chứa nhà thầu đang chấm -> loại khỏi prompt (0 call, cần làm rõ)."""
    from experiment.evaluate.schema import KET_QUA_SOI, VendorContext

    v = ScriptedVision({"[EV:Giá webform]": {"ket_qua": "đạt", "bang_chung": "x"}})
    got = await eval_noi_dung(_nd("Giá webform", "webform"), [_wf("1|Cty DEF|1.15 tỷ")], v,
                              vendor_ctx=VendorContext(ten="Cty ABC"))
    assert got.ket_qua == KET_QUA_SOI and v.calls == []
    assert "không dò được dòng nhà thầu" in got.ghi_chu


async def test_skill_serves_need_routed_to_reference_doc():
    """STRUCT chọn nhầm hsdt_kiem_tra=webform -> luật VẪN phục vụ (khớp theo thành viên ho_so_can).

    Nếu rơi xuống eval chung, prompt sẽ nuốt webform của MỌI nhà thầu mà không có ngữ cảnh luật.
    """
    from experiment.evaluate.schema import VendorContext

    crit = {"nhom": "hop_le", "ten": "Giá khớp webform",
            "hsdt_can_kiem_tra": ["bang_gia", "webform"],
            "noi_dung_can_kiem_tra": [_nd("Giá công bố webform", "webform")]}
    v = ScriptedVision({})     # KHÔNG kịch bản [EV:...] -> eval chung sẽ nổ thành 'lỗi'
    ce = await evaluate_criterion(crit, [_wf()], v, registry=_reg_gia(KET_QUA_DAT),
                                  vendor_ctx=VendorContext(ten="Cty ABC"),
                                  by_type={"webform": [_wf()]})
    assert ce.ket_qua == KET_QUA_DAT
    assert not any("[EV:Giá công bố webform]" in hay for hay, _ in v.calls)


def _nd_ap(noi_dung, hsdt, ap_dung=""):
    return dict(_nd(noi_dung, hsdt), ap_dung=ap_dung)


async def test_gate_mixed_criterion_keeps_general_content():
    """MẤU CHỐT (Claim 2): tiêu chí TRỘN nội dung chung + liên danh -> độc lập VẪN chấm nội dung chung.

    'Đơn ký bởi đại diện hợp pháp' (ap_dung='') áp dụng mọi nhà thầu -> KHÔNG gate; 'ký theo phân
    công liên danh' (ap_dung='lien_danh') -> N/A. Trước đây gate cấp tiêu chí bỏ sót nội dung chung.
    """
    from experiment.evaluate.schema import HINH_THUC_DOC_LAP, KET_QUA_KHONG_AP_DUNG

    crit = {"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ",
            "yeu_cau_goc": "Đơn ký bởi đại diện hợp pháp. Đối với liên danh, ký theo phân công.",
            "hsdt_can_kiem_tra": ["don_du_thau", "thoa_thuan_lien_danh"],
            "noi_dung_can_kiem_tra": [
                _nd_ap("Đơn ký bởi đại diện hợp pháp", "don_du_thau", ""),
                _nd_ap("Liên danh: ký theo phân công", "don_du_thau", "lien_danh")]}
    v = ScriptedVision({"[EV:Đơn ký bởi đại diện hợp pháp]": {"ket_qua": "đạt", "bang_chung": "ký hợp lệ"}})
    ce = await evaluate_criterion(crit, [_page("don_du_thau", "đơn")], v,
                                  profile=_profile(HINH_THUC_DOC_LAP, do_tin=1.0))
    kq = {x.noi_dung_kiem_tra: x.ket_qua for x in ce.verdicts}
    assert kq["Đơn ký bởi đại diện hợp pháp"] == KET_QUA_DAT          # nội dung CHUNG được chấm
    assert kq["Liên danh: ký theo phân công"] == KET_QUA_KHONG_AP_DUNG  # nội dung liên danh -> N/A
    assert ce.ket_qua == KET_QUA_DAT            # roll-up không mất nội dung chung
    assert len(v.calls) == 1                                          # chỉ 1 call cho nội dung chung


async def test_gate_ap_dung_lien_danh_routed_to_shared_doc():
    """Nội dung ap_dung='lien_danh' route vào don_du_thau (không phải thoa_thuan) -> độc lập vẫn N/A."""
    from experiment.evaluate.schema import HINH_THUC_DOC_LAP, KET_QUA_KHONG_AP_DUNG

    v = ScriptedVision({})
    got = await eval_noi_dung(_nd_ap("Ký theo phân công", "don_du_thau", "lien_danh"),
                              [_page("don_du_thau", "đơn")], v,
                              profile=_profile(HINH_THUC_DOC_LAP))
    assert got.ket_qua == KET_QUA_KHONG_AP_DUNG and v.calls == []


async def test_gate_ap_dung_doc_lap_for_lien_danh_vendor():
    """Đối xứng: nội dung ap_dung='doc_lap' + nhà thầu liên danh -> N/A tất định."""
    from experiment.evaluate.schema import HINH_THUC_LIEN_DANH, KET_QUA_KHONG_AP_DUNG

    v = ScriptedVision({})
    got = await eval_noi_dung(_nd_ap("Chỉ dành độc lập", "don_du_thau", "doc_lap"),
                              [_page("don_du_thau", "đơn")], v,
                              profile=_profile(HINH_THUC_LIEN_DANH))
    assert got.ket_qua == KET_QUA_KHONG_AP_DUNG and v.calls == []


async def test_gate_general_content_not_gated_for_lien_danh():
    """Nội dung chung (ap_dung='') -> nhà thầu liên danh vẫn chấm bình thường."""
    from experiment.evaluate.schema import HINH_THUC_LIEN_DANH

    v = ScriptedVision({"[EV:Đơn ký hợp lệ]": {"ket_qua": "đạt", "bang_chung": "ok"}})
    got = await eval_noi_dung(_nd_ap("Đơn ký hợp lệ", "don_du_thau", ""),
                              [_page("don_du_thau", "đơn")], v,
                              profile=_profile(HINH_THUC_LIEN_DANH))
    assert got.ket_qua == KET_QUA_DAT and len(v.calls) == 1


def test_sys_rule_bang_gia_warns_multi_vendor_table():
    """Lọc chỉ ở mức TRANG -> prompt PHẢI cấm lấy dòng nhà thầu khác."""
    from experiment.evaluate.rules.bang_gia_khop_webform import SYS_RULE_BANG_GIA

    assert "NHIỀU nhà thầu" in SYS_RULE_BANG_GIA
    assert "KHÔNG lấy giá của nhà thầu khác" in SYS_RULE_BANG_GIA.replace("TUYỆT ĐỐI ", "")


async def test_cross_doc_when_criterion_declares_extra_docs():
    """Tiêu chí khai thêm tài liệu đối chiếu -> ĐỐI CHIẾU CHÉO, KHÔNG cần cờ doi_chieu_hsdt.

    Ca thật: 'Đối với nhà thầu liên danh, đơn dự thầu phải do ... thành viên đứng đầu ký theo phân
    công trong thỏa thuận liên danh'. SYS_STRUCT (VÍ DỤ 3) dạy nội dung thuộc hồ sơ nhà thầu ->
    can_tra_cuu=false -> RESOLVE không chạy -> doi_chieu_hsdt KHÔNG BAO GIỜ bật. Nếu bám vào cờ đó
    thì model chỉ thấy đơn, không thấy thỏa thuận -> 'cần làm rõ' giả.
    """
    crit = {"nhom": "hop_le", "ten": "Đơn ký theo phân công liên danh",
            "hsdt_can_kiem_tra": ["don_du_thau", "thoa_thuan_lien_danh"],
            "noi_dung_can_kiem_tra": [
                {"noi_dung_kiem_tra": "Ký đúng phân công", "hsdt_kiem_tra": "don_du_thau",
                 "yeu_cau": "người ký khớp phân công", "can_tra_cuu": False,
                 "thong_tin_bo_sung": ""}]}      # KHÔNG có doi_chieu_hsdt
    pages = [_page("don_du_thau", "đơn: Nguyễn Văn A ký"),
             _page("thoa_thuan_lien_danh", "thỏa thuận: Trần Văn B được phân công ký")]
    vision = ScriptedVision({"[EV:Ký đúng phân công]": {"ket_qua": "không đạt",
                                                        "bang_chung": "A ≠ B", "trang": [1]}})
    ce = await evaluate_criterion(crit, pages, vision)
    prompt = vision.calls[-1][0]
    assert "Nguyễn Văn A" in prompt and "Trần Văn B" in prompt   # THẤY CẢ HAI phía
    assert "đối chiếu chéo" in prompt.lower()
    assert ce.ket_qua == KET_QUA_KHONG


async def test_no_cross_when_criterion_declares_single_doc():
    """Chỉ khai 1 hồ sơ -> KHÔNG cross (giữ prompt gọn, hành vi như cũ)."""
    crit = {"nhom": "hop_le", "ten": "Bảo đảm dự thầu",
            "hsdt_can_kiem_tra": ["bao_dam_du_thau"],
            "noi_dung_can_kiem_tra": [_nd("Giá trị bảo lãnh", "bao_dam_du_thau")]}
    vision = ScriptedVision({"[EV:Giá trị bảo lãnh]": {"ket_qua": "đạt", "bang_chung": "6tr"}})
    await evaluate_criterion(crit, [_page("bao_dam_du_thau", "6.100.000")], vision)
    assert "đối chiếu chéo" not in vision.calls[-1][0].lower()


async def test_eval_doi_chieu_hsdt_cross_document():
    """Need cờ doi_chieu_hsdt -> gộp trang loại chính + các loại của tiêu chí, prompt đối chiếu chéo."""
    vision = ScriptedVision({"[EV:Ký đúng phân công]":
                             {"ket_qua": "đạt", "bang_chung": "A ký, thỏa thuận phân công A", "trang": [1]}})
    nd = {"noi_dung_kiem_tra": "Ký đúng phân công", "hsdt_kiem_tra": "don_du_thau",
          "yeu_cau": "người ký khớp phân công trong thỏa thuận liên danh",
          "thong_tin_bo_sung": "", "doi_chieu_hsdt": True}
    pages = [_page("don_du_thau", "đơn: A ký thay liên danh"),
             _page("thoa_thuan_lien_danh", "thỏa thuận: A đại diện ký đơn")]
    v = await eval_noi_dung(nd, pages, vision, extra_types=["don_du_thau", "thoa_thuan_lien_danh"])
    assert v.ket_qua == KET_QUA_DAT
    prompt = vision.calls[-1][0]
    assert "đơn: A ký thay liên danh" in prompt and "thỏa thuận: A đại diện ký" in prompt
    assert "đối chiếu chéo" in prompt.lower()

    # thiếu loại CHÍNH vẫn là thiếu hồ sơ (extra không thay thế được)
    v2 = await eval_noi_dung(nd, [_page("thoa_thuan_lien_danh", "thỏa thuận")], ScriptedVision({}),
                             extra_types=["don_du_thau", "thoa_thuan_lien_danh"])
    assert v2.ket_qua == KET_QUA_THIEU


def test_sys_eval_teaches_new_rules():
    """SYS_EVAL: guard chuẩn '(không có)' + quy tắc so mốc ngày (chuẩn bảng neo có ngày cụ thể)."""
    from experiment.evaluate.prompts import SYS_EVAL
    assert "(không có)" in SYS_EVAL           # guard: chuẩn thiếu -> không kết luận
    assert "mốc" in SYS_EVAL and "ngày" in SYS_EVAL


def _reg_gia(ket_qua=KET_QUA_DAT, ho_so_can=("bang_gia", "webform")):
    """Registry 1 luật giả phạm vi tiêu chí — dùng để khoá cơ chế THAY THẾ."""
    from experiment.evaluate.rules.registry import RuleRegistry, RuleSkill
    from experiment.evaluate.schema import Verdict

    async def handler(by_type, ctx, c, vision_fn, *, nd=None, pkg=None):
        return Verdict(noi_dung_kiem_tra=(nd or {}).get("noi_dung_kiem_tra", "luật"),
                       hsdt_kiem_tra="bang_gia", yeu_cau="", thong_tin_bo_sung="",
                       ket_qua=ket_qua, bang_chung="giá 2 phía khớp", trang=[1], do_tin=0.9,
                       ghi_chu="", nguon_doc=list(ho_so_can))

    reg = RuleRegistry()
    reg.register(RuleSkill(id="luat_gia", ten="luật giả", ho_so_can=list(ho_so_can),
                           can_vendor=False, handler=handler))
    return reg


async def test_rule_REPLACES_need_verdict_no_generic_eval():
    """MẤU CHỐT: luật THAY THẾ kết luận nội dung, KHÔNG bổ sung.

    Nếu còn gọi eval chung cho nội dung này thì ScriptedVision không có kịch bản [EV:...] ->
    AiOutcome error -> verdict 'lỗi' -> roll-up ra 'cần làm rõ' -> test đỏ. Đây chính là bug user
    báo: eval chung chỉ đọc trang bang_gia (không có chữ nào nhắc webform) -> SOI thắng 'đạt'.
    """
    crit = {"nhom": "hop_le", "ten": "Giá khớp webform",
            "hsdt_can_kiem_tra": ["bang_gia", "webform"],
            "noi_dung_can_kiem_tra": [_nd("Giá phải phù hợp webform", "bang_gia")]}
    vision = ScriptedVision({})          # KHÔNG có kịch bản [EV:...] -> eval chung sẽ nổ
    ce = await evaluate_criterion(crit, [_page("bang_gia", "đơn giá 1.2 tỷ")], vision,
                                  registry=_reg_gia(KET_QUA_DAT),
                                  by_type={"bang_gia": [_page("bang_gia", "1.2 tỷ")],
                                           "webform": [_page("webform", "ABC 1.2 tỷ")]})
    assert [v.ket_qua for v in ce.verdicts] == [KET_QUA_DAT]
    assert ce.ket_qua == KET_QUA_DAT
    assert not any("[EV:Giá phải phù hợp webform]" in hay for hay, _ in vision.calls)
    assert ce.verdicts[0].noi_dung_kiem_tra == "Giá phải phù hợp webform"   # mang danh tính nd


async def test_rule_does_not_fire_when_criterion_lacks_doc_set():
    """Tiêu chí 'Bảng giá đúng mẫu' khai [bang_gia] -> luật KHÔNG bắn, eval chung chạy bình thường."""
    crit = {"nhom": "hop_le", "ten": "Bảng giá đúng mẫu",
            "hsdt_can_kiem_tra": ["bang_gia"],
            "noi_dung_can_kiem_tra": [_nd("Đúng mẫu 05C.1", "bang_gia")]}
    vision = ScriptedVision({"[EV:Đúng mẫu 05C.1]": {"ket_qua": "đạt", "bang_chung": "đúng mẫu"}})
    ce = await evaluate_criterion(crit, [_page("bang_gia", "mẫu 05C.1")], vision,
                                  registry=_reg_gia(KET_QUA_KHONG))
    assert ce.ket_qua == KET_QUA_DAT                       # eval chung, KHÔNG dính verdict luật
    assert any("[EV:Đúng mẫu 05C.1]" in hay for hay, _ in vision.calls)


async def test_rule_fires_in_every_matching_criterion_no_fired():
    """Bỏ `fired`: 2 tiêu chí cùng khai đủ bộ hồ sơ -> luật bắn ở CẢ HAI (bug user báo)."""
    crit = {"nhom": "hop_le", "ten": "Giá khớp webform",
            "hsdt_can_kiem_tra": ["bang_gia", "webform"],
            "noi_dung_can_kiem_tra": [_nd("Giá khớp webform", "bang_gia")]}
    reg = _reg_gia(KET_QUA_DAT)
    pages = [_page("bang_gia", "1.2 tỷ")]
    ce1 = await evaluate_criterion(crit, pages, ScriptedVision({}), registry=reg)
    ce2 = await evaluate_criterion(crit, pages, ScriptedVision({}), registry=reg)
    assert ce1.ket_qua == KET_QUA_DAT and ce2.ket_qua == KET_QUA_DAT


async def test_rule_only_serves_needs_routed_to_its_primary_doc():
    """Nội dung route tới hồ sơ khác vẫn chạy eval chung (luật chỉ phục vụ ho_so_can[0])."""
    crit = {"nhom": "hop_le", "ten": "Hỗn hợp",
            "hsdt_can_kiem_tra": ["bang_gia", "webform"],
            "noi_dung_can_kiem_tra": [_nd("Giá khớp webform", "bang_gia"),
                                      _nd("Có đơn dự thầu", "don_du_thau")]}
    vision = ScriptedVision({"[EV:Có đơn dự thầu]": {"ket_qua": "đạt", "bang_chung": "có"}})
    ce = await evaluate_criterion(crit, [_page("don_du_thau", "đơn")], vision,
                                  registry=_reg_gia(KET_QUA_DAT))
    assert [v.ket_qua for v in ce.verdicts] == [KET_QUA_DAT, KET_QUA_DAT]
    assert any("[EV:Có đơn dự thầu]" in hay for hay, _ in vision.calls)


async def test_rule_verdict_khong_dat_marks_loai_on_its_own_criterion():
    """Luật 'không đạt' -> tiêu chí ĐÚNG của nó ra 'không đạt'."""
    crit = {"nhom": "hop_le", "ten": "Giá khớp webform",
            "hsdt_can_kiem_tra": ["bang_gia", "webform"],
            "noi_dung_can_kiem_tra": [_nd("Giá khớp webform", "bang_gia")]}
    ce = await evaluate_criterion(crit, [_page("bang_gia", "1.5 tỷ")], ScriptedVision({}),
                                  registry=_reg_gia(KET_QUA_KHONG))
    assert ce.ket_qua == KET_QUA_KHONG
