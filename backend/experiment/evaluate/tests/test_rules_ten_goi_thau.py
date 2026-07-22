"""Luật ten_goi_thau_khop: tài liệu HSDT ghi tên gói thầu -> phải trùng gói thầu đang xét."""
from experiment.evaluate.rules.registry import PHAM_VI_GOI
from experiment.evaluate.rules.ten_goi_thau_khop import SKILL, extract_goi_thau_lines
from experiment.evaluate.schema import (
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_LOI, PackageContext, PageRecord,
)
from experiment.evaluate.vision import ScriptedVision


def _p(trang, loai, text):
    return PageRecord(file="f.pdf", trang=trang, loai_ho_so=loai, text=text)


_PKG = PackageContext(ten="Mua sắm thiết bị mạng năm 2026", ma_so="G-2026-01")


def test_skill_is_standing_and_needs_pkg():
    assert SKILL.id == "ten_goi_thau_khop"
    assert SKILL.pham_vi == PHAM_VI_GOI
    assert SKILL.can_pkg is True and SKILL.can_vendor is False


def test_extract_goi_thau_lines_normalized_and_page_tagged():
    """Lọc TẤT ĐỊNH dòng nhắc 'gói thầu' (không dấu vẫn bắt), kèm số trang; không nhắc -> rỗng."""
    pages = [_p(2, "don_du_thau", "Kính gửi...\nTham dự Goi thau: Mua sắm thiết bị\nTrân trọng"),
             _p(3, "don_du_thau", "nội dung không liên quan")]
    got = extract_goi_thau_lines(pages)
    assert "Goi thau: Mua sắm thiết bị" in got and "[Trang 2]" in got
    assert "không liên quan" not in got
    assert extract_goi_thau_lines([_p(1, "x", "abc")]) == ""


async def test_handler_no_mention_dat_no_llm():
    """Không tài liệu nào ghi tên gói thầu -> 'đạt' (không có gì để đối chiếu), 0 call LLM."""
    vision = ScriptedVision({})
    by_type = {"bang_gia": [_p(1, "bang_gia", "đơn giá 1.2 tỷ")]}
    v = await SKILL.handler(by_type, None, {}, vision, pkg=_PKG)
    assert v.ket_qua == KET_QUA_DAT and vision.calls == []
    assert "gói thầu" in v.ghi_chu


async def test_handler_mention_match_dat():
    """Tài liệu ghi đúng tên gói -> 'đạt'; prompt phải chứa tên gói đang xét + dòng ứng viên."""
    vision = ScriptedVision({"[RULE:ten_goi_thau_khop]": {
        "ket_qua": "đạt", "bang_chung": "đơn ghi đúng tên gói", "trang": [1], "do_tin": 0.9}})
    by_type = {"don_du_thau": [_p(1, "don_du_thau",
                                  "Gói thầu: Mua sắm thiết bị mạng năm 2026")]}
    v = await SKILL.handler(by_type, None, {}, vision, pkg=_PKG)
    assert v.ket_qua == KET_QUA_DAT
    assert v.nguon_doc == ["don_du_thau"]                   # chỉ tài liệu có nhắc gói thầu
    hay = vision.calls[-1][0]
    assert "Mua sắm thiết bị mạng năm 2026" in hay and "G-2026-01" in hay
    assert "don_du_thau" in hay


async def test_handler_mention_mismatch_khong_dat():
    """Tài liệu ghi tên gói KHÁC -> 'không đạt', bằng chứng nêu tài liệu lệch."""
    vision = ScriptedVision({"[RULE:ten_goi_thau_khop]": {
        "ket_qua": "không đạt",
        "tai_lieu_lech": [{"loai_ho_so": "bao_dam_du_thau",
                           "ten_ghi": "Gói thầu xây lắp trụ sở", "trang": [2]}],
        "bang_chung": "bảo đảm dự thầu ghi 'Gói thầu xây lắp trụ sở'", "trang": [2]}})
    by_type = {"don_du_thau": [_p(1, "don_du_thau", "Gói thầu: Mua sắm thiết bị mạng năm 2026")],
               "bao_dam_du_thau": [_p(2, "bao_dam_du_thau", "bảo lãnh cho Gói thầu xây lắp trụ sở")]}
    v = await SKILL.handler(by_type, None, {}, vision, pkg=_PKG)
    assert v.ket_qua == KET_QUA_KHONG
    assert "xây lắp trụ sở" in v.bang_chung
    assert set(v.nguon_doc) == {"don_du_thau", "bao_dam_du_thau"}


async def test_handler_ai_error_becomes_loi():
    vision = ScriptedVision({})
    by_type = {"don_du_thau": [_p(1, "don_du_thau", "tham dự gói thầu ABC")]}
    v = await SKILL.handler(by_type, None, {}, vision, pkg=_PKG)
    assert v.ket_qua == KET_QUA_LOI
