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


def test_skill_metadata_and_kich_hoat():
    assert SKILL.id == "bang_gia_khop_webform" and SKILL.can_vendor is True
    assert SKILL.ho_so_can == ["bang_gia", "webform"]
    crit_gia = {"ten": "Bảng chào giá", "noi_dung_can_kiem_tra": [
        {"noi_dung_kiem_tra": "Đúng mẫu", "hsdt_kiem_tra": "Bang_Gia"}]}
    assert SKILL.kich_hoat(crit_gia) is True
    assert SKILL.kich_hoat({"ten": "Khác", "noi_dung_can_kiem_tra": []}) is False


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
