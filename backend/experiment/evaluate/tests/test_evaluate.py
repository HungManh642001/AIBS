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


async def test_criterion_rollup_blocking_fail_marks_loai():
    crit = {"nhom": "hop_le", "ten": "Bảo đảm dự thầu", "tien_quyet": True,
            "noi_dung_can_kiem_tra": [_nd("Giá trị bảo lãnh", "bao_dam_du_thau")]}
    vision = ScriptedVision({"[EV:Giá trị bảo lãnh]":
                             {"ket_qua": "không đạt", "bang_chung": "3 triệu < 6.1tr", "trang": [1]}})
    ce = await evaluate_criterion(crit, [_page("bao_dam_du_thau", "bảo lãnh 3.000.000")], vision)
    assert ce.ket_qua == KET_QUA_KHONG and ce.loai is True


def _rule_reg(ket_qua):
    """Registry 1 luật giả trả verdict ket_qua cho tiêu chí bất kỳ — bơm verdict vào roll-up."""
    from experiment.evaluate.rules.registry import RuleRegistry, RuleSkill
    from experiment.evaluate.schema import Verdict

    async def handler(by_type, ctx, c, vision_fn):
        return Verdict(noi_dung_kiem_tra="luật", hsdt_kiem_tra="don_du_thau", yeu_cau="",
                       thong_tin_bo_sung="", ket_qua=ket_qua, bang_chung="", trang=[],
                       do_tin=0.0, ghi_chu="")

    reg = RuleRegistry()
    reg.register(RuleSkill(id="luat_gia", ten="luật", ho_so_can=["don_du_thau"], can_vendor=False,
                           kich_hoat=lambda c: True, handler=handler))
    return reg


async def test_rollup_na_is_neutral():
    """N/A trung tính: [đạt, N/A] -> tiêu chí 'đạt' (N/A không kéo xuống 'cần làm rõ')."""
    from experiment.evaluate.schema import KET_QUA_KHONG_AP_DUNG

    crit = {"nhom": "hop_le", "ten": "Đơn dự thầu", "tien_quyet": True,
            "noi_dung_can_kiem_tra": [_nd("Có đơn dự thầu", "don_du_thau")]}
    vision = ScriptedVision({"[EV:Có đơn dự thầu]": {"ket_qua": "đạt", "bang_chung": "có", "trang": [1]}})
    ce = await evaluate_criterion(crit, [_page("don_du_thau", "đơn")], vision,
                                  registry=_rule_reg(KET_QUA_KHONG_AP_DUNG))
    assert [v.ket_qua for v in ce.verdicts] == [KET_QUA_DAT, KET_QUA_KHONG_AP_DUNG]
    assert ce.ket_qua == KET_QUA_DAT and ce.loai is False


async def test_rollup_all_na_criterion_is_na_not_loai():
    """Toàn bộ verdict N/A -> tiêu chí 'không áp dụng', loai=False DÙ tien_quyet=True."""
    from experiment.evaluate.schema import KET_QUA_KHONG_AP_DUNG

    crit = {"nhom": "hop_le", "ten": "Thỏa thuận liên danh", "tien_quyet": True,
            "noi_dung_can_kiem_tra": []}
    ce = await evaluate_criterion(crit, [_page("don_du_thau", "đơn")], ScriptedVision({}),
                                  registry=_rule_reg(KET_QUA_KHONG_AP_DUNG))
    assert ce.ket_qua == KET_QUA_KHONG_AP_DUNG and ce.loai is False


async def test_rollup_na_plus_khong_dat_still_loai():
    """N/A KHÔNG che 'không đạt': tiên quyết -> vẫn loại."""
    from experiment.evaluate.schema import KET_QUA_KHONG_AP_DUNG

    crit = {"nhom": "hop_le", "ten": "Đơn dự thầu", "tien_quyet": True,
            "noi_dung_can_kiem_tra": [_nd("Có đơn dự thầu", "don_du_thau")]}
    vision = ScriptedVision({"[EV:Có đơn dự thầu]": {"ket_qua": "không đạt", "bang_chung": "x", "trang": [1]}})
    ce = await evaluate_criterion(crit, [_page("don_du_thau", "đơn")], vision,
                                  registry=_rule_reg(KET_QUA_KHONG_AP_DUNG))
    assert ce.ket_qua == KET_QUA_KHONG and ce.loai is True


async def test_rollup_empty_verdicts_still_soi():
    """Tiêu chí KHÔNG có verdict nào -> 'cần làm rõ' (giữ hành vi cũ, không thành N/A)."""
    from experiment.evaluate.schema import KET_QUA_SOI

    ce = await evaluate_criterion({"nhom": "hop_le", "ten": "X", "noi_dung_can_kiem_tra": []},
                                  [], ScriptedVision({}))
    assert ce.ket_qua == KET_QUA_SOI and ce.loai is False


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

    crit = {"nhom": "hop_le", "ten": "Đơn dự thầu", "tien_quyet": False,
            "noi_dung_can_kiem_tra": [_nd("Có đơn dự thầu", "don_du_thau")]}
    v = ScriptedVision({"[EV:Có đơn dự thầu]": {"ket_qua": "đạt", "bang_chung": "có", "trang": [1]}})
    await evaluate_criterion(crit, [_page("don_du_thau", "đơn")], v,
                             vendor_ctx=VendorContext(ten="Công ty ABC"),
                             profile=_profile(HINH_THUC_DOC_LAP))
    assert "Công ty ABC" in v.calls[-1][0] and "độc lập" in v.calls[-1][0]


async def test_criterion_passes_yeu_cau_goc_and_siblings_to_each_need():
    """1 yeu_cau_goc -> N yeu_cau: mỗi call thấy nguyên văn gốc + đúng tên anh em (không có tên nó)."""
    crit = {"nhom": "hop_le", "ten": "Bảo đảm dự thầu", "tien_quyet": True,
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


async def test_criterion_rule_verdict_joins_rollup():
    """Verdict luật append vào verdicts tiêu chí -> vào roll-up: luật không đạt + tiên quyết -> loại."""
    from experiment.evaluate.rules.registry import RuleRegistry, RuleSkill
    from experiment.evaluate.schema import Verdict

    async def handler(by_type, ctx, c, vision_fn):
        assert [p.trang for p in by_type["don_du_thau"]] == [1]   # luật thấy by_type
        return Verdict(noi_dung_kiem_tra="Người ký khớp ĐKKD", hsdt_kiem_tra="don_du_thau",
                       yeu_cau="", thong_tin_bo_sung="", ket_qua="không đạt",
                       bang_chung="ký: A ≠ đại diện: B", trang=[1], do_tin=0.9, ghi_chu="",
                       nguon_doc=["don_du_thau", "tu_cach_phap_ly"])

    reg = RuleRegistry()
    reg.register(RuleSkill(id="luat_gia", ten="Người ký khớp ĐKKD", ho_so_can=["don_du_thau"],
                           can_vendor=False, kich_hoat=lambda c: c.get("ten") == "Đơn dự thầu",
                           handler=handler))
    crit = {"nhom": "hop_le", "ten": "Đơn dự thầu", "tien_quyet": True,
            "noi_dung_can_kiem_tra": [_nd("Có đơn dự thầu", "don_du_thau")]}
    vision = ScriptedVision({"[EV:Có đơn dự thầu]": {"ket_qua": "đạt", "bang_chung": "có đơn", "trang": [1]}})
    pages = [_page("don_du_thau", "đơn dự thầu ký bởi A")]
    fired: set[str] = set()

    ce = await evaluate_criterion(crit, pages, vision, registry=reg, fired=fired)
    assert [v.noi_dung_kiem_tra for v in ce.verdicts] == ["Có đơn dự thầu", "Người ký khớp ĐKKD"]
    assert ce.ket_qua == KET_QUA_KHONG and ce.loai is True    # luật kéo roll-up
    assert fired == {"luat_gia"}

    # tiêu chí sau cùng vendor: luật KHÔNG bắn lần 2
    ce2 = await evaluate_criterion(crit, pages, vision, registry=reg, fired=fired)
    assert [v.noi_dung_kiem_tra for v in ce2.verdicts] == ["Có đơn dự thầu"]
