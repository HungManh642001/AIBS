"""B3 — luật bang_gia_khop_webform: bảng giá vendor ↔ dòng đúng nhà thầu trong webform chung."""
from experiment.evaluate.rules.bang_gia_khop_webform import SKILL, find_vendor_pages
from experiment.evaluate.schema import (
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_SOI, KET_QUA_THIEU, PageRecord, VendorContext,
)
from experiment.evaluate.vision import ScriptedVision


def _p(trang, text, loai="webform"):
    return PageRecord(file="webform.pdf", trang=trang, loai_ho_so=loai, text=text)


_WEBFORM = [
    _p(1, "KẾT QUẢ MỞ THẦU\nSTT | Nhà thầu | Giá dự thầu"),
    _p(2, "1 | Công ty TNHH Xây dựng ABC | 1.200.000.000\n2 | Công ty CP DEF | 1.150.000.000"),
    _p(3, "3 | Liên danh GHI-JKL (MST 0312345678) | 1.100.000.000"),
]


def test_find_vendor_pages_by_name_normalized():
    """Khớp tên bỏ dấu/hoa thường; chỉ trả trang chứa nhà thầu đang chấm."""
    ctx = VendorContext(ten="Công ty TNHH XÂY DỰNG abc")
    assert [p.trang for p in find_vendor_pages(_WEBFORM, ctx)] == [2]


def test_find_vendor_pages_by_mst_and_alias():
    assert [p.trang for p in find_vendor_pages(_WEBFORM, VendorContext(ten="Không khớp tên",
                                                                       ma_so_thue="0312345678"))] == [3]
    assert [p.trang for p in find_vendor_pages(_WEBFORM, VendorContext(ten="XYZ",
                                                                       aliases=["công ty cp def"]))] == [2]


def test_find_vendor_pages_no_match_empty():
    assert find_vendor_pages(_WEBFORM, VendorContext(ten="Công ty Ma", ma_so_thue="999")) == []
    assert find_vendor_pages([], VendorContext(ten="ABC")) == []


_CTX = VendorContext(ten="Công ty TNHH Xây dựng ABC")
_BY_TYPE = {
    "bang_gia": [PageRecord(file="bg.pdf", trang=1, loai_ho_so="bang_gia",
                            text="BẢNG CHÀO GIÁ\nTổng: 1.200.000.000 VNĐ")],
    "webform": _WEBFORM,
}


async def test_handler_verdict_carries_nd_identity():
    """Luật THAY THẾ kết luận nội dung -> verdict phải mang danh tính nội dung + giữ chuỗi audit."""
    from experiment.evaluate.rules.bang_gia_khop_webform import handler
    from experiment.evaluate.schema import VendorContext

    nd = {"noi_dung_kiem_tra": "Giá phải phù hợp webform", "hsdt_kiem_tra": "bang_gia",
          "yeu_cau": "Giá dự thầu khớp giá công bố trên webform", "thong_tin_bo_sung": "",
          "nguon": "E-BDL 26.1"}
    by_type = {"bang_gia": [_p(1, "Tổng giá: 1.200.000.000", "bang_gia")],
               "webform": [_p(1, "Công ty ABC | 1.200.000.000")]}
    vision = ScriptedVision({"[RULE:bang_gia_khop_webform]":
                             {"ket_qua": "đạt", "bang_chung": "1.2 tỷ = 1.2 tỷ", "trang": [1]}})
    v = await handler(by_type, VendorContext(ten="Công ty ABC"), {}, vision, nd=nd)

    assert v.noi_dung_kiem_tra == "Giá phải phù hợp webform"
    assert v.yeu_cau == "Giá dự thầu khớp giá công bố trên webform"
    assert v.nguon_hsmt == "E-BDL 26.1"                        # chuỗi audit không đứt
    assert v.nguon_doc == ["bang_gia", "webform"]
    assert "Giá dự thầu khớp giá công bố trên webform" in vision.calls[-1][0]   # prompt hỏi đúng câu


async def test_handler_without_nd_falls_back_to_rule_label():
    from experiment.evaluate.rules.bang_gia_khop_webform import _TEN, handler
    from experiment.evaluate.schema import VendorContext

    by_type = {"bang_gia": [_p(1, "1.2 tỷ", "bang_gia")],
               "webform": [_p(1, "Công ty ABC | 1.2 tỷ")]}
    vision = ScriptedVision({"[RULE:bang_gia_khop_webform]": {"ket_qua": "đạt", "bang_chung": "ok"}})
    v = await handler(by_type, VendorContext(ten="Công ty ABC"), {}, vision)
    assert v.noi_dung_kiem_tra == _TEN and v.nguon_hsmt == ""


def test_skill_metadata_and_matching():
    """Chỉ khớp tiêu chí KHAI ĐỦ [bang_gia, webform] — tiêu chí 'đúng mẫu' chỉ khai bang_gia -> không.

    Trước đây predicate là 'có nội dung nào dùng bang_gia' -> khớp MỌI tiêu chí đụng bảng giá ->
    luật bắn nhầm tiêu chí đầu tiên, còn tiêu chí thật (giá khớp webform) bị bỏ -> 'cần làm rõ'.
    """
    from experiment.evaluate.rules.registry import PHAM_VI_TIEU_CHI, RuleRegistry

    assert SKILL.id == "bang_gia_khop_webform" and SKILL.can_vendor is True
    assert SKILL.ho_so_can == ["bang_gia", "webform"]
    assert SKILL.pham_vi == PHAM_VI_TIEU_CHI

    reg = RuleRegistry()
    reg.register(SKILL)
    assert reg.matching({"ten": "Bảng chào giá đúng mẫu", "hsdt_can_kiem_tra": ["bang_gia"]}) == []
    assert [s.id for s in reg.matching({"ten": "Giá khớp webform",
                                        "hsdt_can_kiem_tra": ["Bang_Gia", "WebForm"]})] \
        == ["bang_gia_khop_webform"]
    assert reg.matching({"ten": "Khác", "hsdt_can_kiem_tra": []}) == []


async def test_handler_dat_va_lech():
    ok = ScriptedVision({"[RULE:bang_gia_khop_webform]": {
        "ket_qua": "đạt", "bang_chung": "bảng giá 1.200.000.000 = webform 1.200.000.000 (tr 2)",
        "trang": [1], "do_tin": 0.9}})
    v = await SKILL.handler(_BY_TYPE, _CTX, {}, ok)
    assert v.ket_qua == KET_QUA_DAT and v.nguon_doc == ["bang_gia", "webform"]
    prompt = ok.calls[-1][0]
    assert "1 | Công ty TNHH Xây dựng ABC | 1.200.000.000" in prompt  # trang webform ĐÃ LỌC
    assert "Liên danh GHI-JKL" not in prompt                          # nhà thầu khác KHÔNG vào prompt
    assert "Công ty TNHH Xây dựng ABC" in prompt                      # danh tính vendor có mặt
    assert ok.calls[-1][1] == 0                                       # text-only

    lech = ScriptedVision({"[RULE:bang_gia_khop_webform]": {
        "ket_qua": "không đạt", "bang_chung": "bảng giá 1.3 tỷ ≠ webform 1.2 tỷ", "trang": [1]}})
    v2 = await SKILL.handler(_BY_TYPE, _CTX, {}, lech)
    assert v2.ket_qua == KET_QUA_KHONG


async def test_handler_khong_do_duoc_dong_soi_no_llm():
    vision = ScriptedVision({})
    ctx_la = VendorContext(ten="Công ty Ma")
    v = await SKILL.handler(_BY_TYPE, ctx_la, {}, vision)
    assert v.ket_qua == KET_QUA_SOI and "không dò được" in v.ghi_chu.lower()
    assert vision.calls == []                                         # no-fab: KHÔNG gọi LLM


async def test_handler_thieu_ho_so():
    vision = ScriptedVision({})
    v = await SKILL.handler({"bang_gia": _BY_TYPE["bang_gia"]}, _CTX, {}, vision)
    assert v.ket_qua == KET_QUA_THIEU and "webform" in v.bang_chung
    v2 = await SKILL.handler({"webform": _WEBFORM}, _CTX, {}, vision)
    assert v2.ket_qua == KET_QUA_THIEU and "bang_gia" in v2.bang_chung
    assert vision.calls == []
