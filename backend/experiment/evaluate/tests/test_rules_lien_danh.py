"""Luật lien_danh_phan_cong_khop_bang_gia: phân công TTLĐ nêu rõ hạng mục + tỷ lệ % khớp bảng giá.

Số học tách khỏi LLM: `doi_chieu_phan_cong` là hàm thuần -> test kỹ mọi nhánh không cần proxy.
"""
from experiment.evaluate.rules.lien_danh_phan_cong import (
    DUNG_SAI_DIEM_PT, SKILL, doi_chieu_phan_cong, lien_danh_prompt,
)
from experiment.evaluate.rules.registry import PHAM_VI_GOI
from experiment.evaluate.schema import (
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_KHONG_AP_DUNG, KET_QUA_LOI, KET_QUA_SOI, KET_QUA_THIEU,
    PageRecord,
)
from experiment.evaluate.vision import ScriptedVision


def _p(trang, loai, text):
    return PageRecord(file="f.pdf", trang=trang, loai_ho_so=loai, text=text)


def _tv(ten, tong_tien, ty_le_khai, neu_ro=True, hang_muc=None):
    return {"ten": ten, "neu_ro_hang_muc": neu_ro, "mo_ta_cong_viec": "cung cấp",
            "hang_muc": hang_muc or [{"ten": "HM", "thanh_tien": tong_tien}],
            "tong_tien": tong_tien, "ty_le_khai": ty_le_khai}


def _data(*thanh_vien, tong=10_000_000_000.0):
    return {"tong_gia_tri_lien_danh": tong, "thanh_vien": list(thanh_vien)}


def test_dung_sai_la_mot_phan_muoi_diem_phan_tram():
    assert DUNG_SAI_DIEM_PT == 0.1


def test_ty_le_khop_thi_dat():
    ket_qua, bc, _ = doi_chieu_phan_cong(
        _data(_tv("Cty A", 6_000_000_000, 60.0), _tv("Cty B", 4_000_000_000, 40.0)))
    assert ket_qua == KET_QUA_DAT
    assert "Cty A" in bc and "60,0%" in bc          # bằng chứng in cả 2 số cho chuyên gia đối soát


def test_lech_qua_dung_sai_thi_khong_dat():
    ket_qua, bc, _ = doi_chieu_phan_cong(
        _data(_tv("Cty A", 6_000_000_000, 60.0), _tv("Cty B", 4_000_000_000, 45.0)))
    assert ket_qua == KET_QUA_KHONG
    assert "Cty B" in bc and "45,0%" in bc and "40,0%" in bc


def test_lech_trong_dung_sai_van_dat():
    """TTLĐ ghi tròn 60% mà bảng giá ra 59,95% -> làm tròn 1 chữ số = 60,0%, không báo lệch."""
    ket_qua, _, _ = doi_chieu_phan_cong(
        _data(_tv("Cty A", 5_995_000_000, 60.0), _tv("Cty B", 4_005_000_000, 40.0)))
    assert ket_qua == KET_QUA_DAT


def test_khong_neu_ro_hang_muc_thi_khong_dat():
    ket_qua, bc, ghi_chu = doi_chieu_phan_cong(
        _data(_tv("Cty A", 6_000_000_000, 60.0),
              _tv("Cty B", 4_000_000_000, 40.0, neu_ro=False)))
    assert ket_qua == KET_QUA_KHONG
    assert "Cty B" in ghi_chu and "hạng mục" in ghi_chu
    assert "Cty B" in bc


def test_tong_thanh_vien_lech_tong_lien_danh_thi_soi():
    """Σ tiền thành viên lệch >2% tổng liên danh -> nghi bóc thiếu hạng mục, KHÔNG dám kết luận."""
    ket_qua, _, ghi_chu = doi_chieu_phan_cong(
        _data(_tv("Cty A", 6_000_000_000, 60.0), _tv("Cty B", 3_000_000_000, 40.0)))
    assert ket_qua == KET_QUA_SOI
    assert "tổng" in ghi_chu


def test_tong_lien_danh_bang_khong_thi_soi():
    ket_qua, _, ghi_chu = doi_chieu_phan_cong(_data(_tv("Cty A", 0, 60.0), tong=0))
    assert ket_qua == KET_QUA_SOI and "tổng" in ghi_chu


def test_khong_co_thanh_vien_thi_soi():
    ket_qua, _, ghi_chu = doi_chieu_phan_cong(_data())
    assert ket_qua == KET_QUA_SOI and "thành viên" in ghi_chu


# ---- handler / skill ----

_TTLD = [_p(1, "thoa_thuan_lien_danh", "BẢNG PHÂN CÔNG: Cty A 60%, Cty B 40%")]
_GIA = [_p(1, "bang_gia", "Máy chủ 6.000.000.000; UPS 4.000.000.000")]


def test_skill_is_standing_cross_doc():
    assert SKILL.id == "lien_danh_phan_cong_khop_bang_gia"
    assert SKILL.pham_vi == PHAM_VI_GOI
    assert SKILL.ho_so_can == ["thoa_thuan_lien_danh", "bang_gia"]
    assert SKILL.can_vendor is False and SKILL.can_pkg is False


def test_prompt_caps_bang_gia_rong_hon_ttld():
    ttld = "T" * 2995 + "MOC_TTLD"                          # mốc nằm sau ký tự thứ 3000
    gia = "G" * 2990 + "MOC_GIA_QUA_3000" + "G" * 3000 + "MOC_GIA_QUA_6000"
    p = lien_danh_prompt(ttld, gia)
    assert "[RULE:lien_danh_phan_cong]" in p
    assert "MOC_TTLD" not in p                              # TTLĐ cắt ở 3000
    assert "MOC_GIA_QUA_3000" in p                          # bảng giá giữ được phần quá 3000
    assert "MOC_GIA_QUA_6000" not in p                      # nhưng vẫn cắt ở 6000


async def test_handler_khong_co_ttld_la_khong_ap_dung():
    """Nhà thầu độc lập (không có TTLĐ) -> 'không áp dụng', KHÔNG gọi LLM, không sinh nhiễu."""
    vision = ScriptedVision({})
    v = await SKILL.handler({"bang_gia": _GIA}, None, {}, vision)
    assert v.ket_qua == KET_QUA_KHONG_AP_DUNG and vision.calls == []


async def test_handler_co_ttld_thieu_bang_gia_la_thieu_ho_so():
    vision = ScriptedVision({})
    v = await SKILL.handler({"thoa_thuan_lien_danh": _TTLD}, None, {}, vision)
    assert v.ket_qua == KET_QUA_THIEU and "bang_gia" in v.bang_chung
    assert vision.calls == []


async def test_handler_dat_khi_ty_le_khop():
    vision = ScriptedVision({"[RULE:lien_danh_phan_cong]": {
        "tong_gia_tri_lien_danh": 10_000_000_000,
        "thanh_vien": [_tv("Cty A", 6_000_000_000, 60.0), _tv("Cty B", 4_000_000_000, 40.0)],
        "trang": [1], "ghi_chu": ""}})
    v = await SKILL.handler({"thoa_thuan_lien_danh": _TTLD, "bang_gia": _GIA}, None, {}, vision)
    assert v.ket_qua == KET_QUA_DAT
    assert v.nguon_doc == ["thoa_thuan_lien_danh", "bang_gia"]
    assert "Cty A" in v.bang_chung and "Cty B" in v.bang_chung
    hay = vision.calls[-1][0]
    assert "BẢNG PHÂN CÔNG" in hay and "Máy chủ" in hay   # cả 2 tài liệu vào prompt


async def test_handler_khong_dat_khi_lech():
    vision = ScriptedVision({"[RULE:lien_danh_phan_cong]": {
        "tong_gia_tri_lien_danh": 10_000_000_000,
        "thanh_vien": [_tv("Cty A", 6_000_000_000, 55.0), _tv("Cty B", 4_000_000_000, 45.0)],
        "trang": [1]}})
    v = await SKILL.handler({"thoa_thuan_lien_danh": _TTLD, "bang_gia": _GIA}, None, {}, vision)
    assert v.ket_qua == KET_QUA_KHONG


async def test_handler_ai_error_becomes_loi():
    vision = ScriptedVision({})
    v = await SKILL.handler({"thoa_thuan_lien_danh": _TTLD, "bang_gia": _GIA}, None, {}, vision)
    assert v.ket_qua == KET_QUA_LOI
