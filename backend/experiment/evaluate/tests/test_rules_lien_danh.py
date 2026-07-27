"""Luật lien_danh_phan_cong_khop_bang_gia: phân công TTLĐ nêu rõ hạng mục + tỷ lệ % khớp bảng giá.

Số học tách khỏi LLM: `doi_chieu_phan_cong` là hàm thuần -> test kỹ mọi nhánh không cần proxy.
"""
from experiment.evaluate.rules.lien_danh_phan_cong import (
    DUNG_SAI_DIEM_PT, SKILL, bang_gia_prompt, doi_chieu_phan_cong, ttld_prompt,
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


def test_ghi_chu_neu_ro_so_tien_chua_phan_cong():
    """Đọc theo chunk thì BIẾT chính xác bao nhiêu tiền chưa gán cho ai — ghi chú phải nói ra.

    Thông điệp cũ ('có thể còn hạng mục chưa phân công HOẶC bảng giá bóc thiếu') bắt chuyên gia tự
    đoán; khi có số liệu thì nêu thẳng số tiền để họ dò đúng chỗ.
    """
    d = _data(_tv("Cty A", 6_000_000_000, 60.0), _tv("Cty B", 3_500_000_000, 40.0))
    d["tien_chua_phan_cong"] = 500_000_000          # 5% tổng
    ket_qua, _, ghi_chu = doi_chieu_phan_cong(d)
    assert ket_qua == KET_QUA_SOI
    assert "500.000.000" in ghi_chu and "chưa gán" in ghi_chu


def test_hang_muc_chua_phan_cong_khong_dang_ke_van_ket_luan():
    """Vụn nhỏ (<=2%, vd dòng làm tròn) không được chặn kết luận."""
    d = _data(_tv("Cty A", 6_000_000_000, 60.0), _tv("Cty B", 3_900_000_000, 39.0))
    d["tien_chua_phan_cong"] = 100_000_000          # 1% tổng
    ket_qua, _, _ = doi_chieu_phan_cong(d)
    assert ket_qua == KET_QUA_DAT


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


def test_prompt_ttld_van_cap_con_bang_gia_thi_khong():
    """TTLĐ ngắn -> cap được. Bảng giá KHÔNG cap ở prompt: độ dài do bước chia chunk lo."""
    p_ttld = ttld_prompt("T" * 2995 + "MOC_TTLD")
    assert "[RULE:lien_danh_ttld]" in p_ttld and "MOC_TTLD" not in p_ttld

    p_gia = bang_gia_prompt("G" * 20000 + "MOC_CUOI", [{"ten": "Cty A", "mo_ta_cong_viec": "máy chủ"}])
    assert "[RULE:lien_danh_bang_gia]" in p_gia
    assert "MOC_CUOI" in p_gia                              # nguyên chunk, không cắt
    assert "Cty A" in p_gia and "máy chủ" in p_gia          # kèm phân công để gán hạng mục


def _vision_2_giai_doan(thanh_vien, hang_muc, dong_tong=None, tong=10_000_000_000):
    return ScriptedVision({
        "[RULE:lien_danh_ttld]": {"thanh_vien": thanh_vien, "trang": [1]},
        "[RULE:lien_danh_bang_gia]": {
            "hang_muc": hang_muc,
            "dong_tong": dong_tong if dong_tong is not None
            else [{"nhan": "Tổng cộng", "gia_tri": tong}]},
    })


def _tv_ttld(ten, ty_le, neu_ro=True):
    return {"ten": ten, "mo_ta_cong_viec": "cung cấp", "neu_ro_hang_muc": neu_ro,
            "ty_le_khai": ty_le}


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


async def test_handler_moi_thanh_vien_mo_ho_thi_khong_doc_bang_gia():
    """Không ai nêu rõ hạng mục -> điều kiện tiền đề đã hỏng, đọc bảng giá là phí call."""
    vision = _vision_2_giai_doan([_tv_ttld("Cty A", 60.0, neu_ro=False),
                                  _tv_ttld("Cty B", 40.0, neu_ro=False)], [])
    v = await SKILL.handler({"thoa_thuan_lien_danh": _TTLD, "bang_gia": _GIA}, None, {}, vision)
    assert v.ket_qua == KET_QUA_KHONG
    assert len(vision.calls) == 1                           # chỉ đọc TTLĐ
    assert "[RULE:lien_danh_bang_gia]" not in vision.calls[0][0]


async def test_handler_dat_khi_ty_le_khop():
    vision = _vision_2_giai_doan(
        [_tv_ttld("Cty A", 60.0), _tv_ttld("Cty B", 40.0)],
        [{"stt": "1", "ten": "Máy chủ", "thanh_tien": 6_000_000_000, "thanh_vien": "Cty A"},
         {"stt": "2", "ten": "UPS", "thanh_tien": 4_000_000_000, "thanh_vien": "Cty B"}])
    v = await SKILL.handler({"thoa_thuan_lien_danh": _TTLD, "bang_gia": _GIA}, None, {}, vision)
    assert v.ket_qua == KET_QUA_DAT
    assert v.nguon_doc == ["thoa_thuan_lien_danh", "bang_gia"]
    assert "Cty A" in v.bang_chung and "Cty B" in v.bang_chung
    assert len(vision.calls) == 2                           # 1 TTLĐ + 1 chunk bảng giá


async def test_handler_khong_dat_khi_lech():
    vision = _vision_2_giai_doan(
        [_tv_ttld("Cty A", 55.0), _tv_ttld("Cty B", 45.0)],
        [{"stt": "1", "ten": "Máy chủ", "thanh_tien": 6_000_000_000, "thanh_vien": "Cty A"},
         {"stt": "2", "ten": "UPS", "thanh_tien": 4_000_000_000, "thanh_vien": "Cty B"}])
    v = await SKILL.handler({"thoa_thuan_lien_danh": _TTLD, "bang_gia": _GIA}, None, {}, vision)
    assert v.ket_qua == KET_QUA_KHONG


class _VisionTheoChunk:
    """Mỗi chunk trả hạng mục RIÊNG (như bảng thật) — kiểm được việc cộng dồn qua nhiều chunk."""

    def __init__(self, thanh_vien, tien_moi_chunk, tong):
        self.thanh_vien = thanh_vien
        self.tien = tien_moi_chunk
        self.tong = tong
        self.calls: list[str] = []
        self._i = 0

    async def __call__(self, system, prompt, images=(), validate=None, **_kw):
        from services.ai_client import AiOutcome
        self.calls.append(prompt)
        if "[RULE:lien_danh_ttld]" in prompt:
            return AiOutcome("ok", {"thanh_vien": self.thanh_vien, "trang": [1], "ghi_chu": ""},
                             "scripted")
        i, self._i = self._i, self._i + 1
        ten_tv = self.thanh_vien[i % len(self.thanh_vien)]["ten"]
        d = {"hang_muc": [{"stt": str(i + 1), "ten": f"HM{i + 1}",
                           "thanh_tien": self.tien, "thanh_vien": ten_tv}],
             "dong_tong": [{"nhan": "Tổng cộng", "gia_tri": self.tong}] if i == 0 else []}
        return AiOutcome("ok", validate(d) if validate else d, "scripted")


async def test_handler_bang_gia_dai_khong_mat_trang_nao():
    """BUG ĐANG SỬA: cap 6000 nuốt 9% bảng giá thật -> tổng sai. Mọi trang PHẢI vào prompt."""
    trang_dai = [_p(i, "bang_gia", f"MOC_TRANG_{i} " + "x" * 4000) for i in range(1, 16)]
    # 15 trang, ngân sách 6000 -> 15 chunk (mỗi trang > 4000 nên không gộp được 2 trang)
    vision = _VisionTheoChunk([_tv_ttld("Cty A", 50.0), _tv_ttld("Cty B", 50.0)],
                              tien_moi_chunk=1_000_000_000, tong=15_000_000_000)
    v = await SKILL.handler({"thoa_thuan_lien_danh": _TTLD, "bang_gia": trang_dai}, None, {},
                            vision)
    da_gui = "\n".join(vision.calls)
    for i in range(1, 16):
        assert f"MOC_TRANG_{i}" in da_gui                   # KHÔNG trang nào bị bỏ
    assert len(vision.calls) == 16                          # 1 TTLĐ + 15 chunk
    # 15 hạng mục x 1 tỷ chia đều 2 thành viên (8/7) -> tỷ lệ 53,3% / 46,7% khác khai 50/50
    assert v.ket_qua == KET_QUA_KHONG
    assert "8.000.000.000" in v.bang_chung                  # đã cộng dồn qua các chunk


async def test_handler_cong_don_dung_qua_nhieu_chunk():
    """Tỷ lệ khai đúng với tổng đã cộng dồn từ MỌI chunk -> 'đạt' (bằng chứng cho cả 2 phía)."""
    trang_dai = [_p(i, "bang_gia", "x" * 4000) for i in range(1, 11)]
    vision = _VisionTheoChunk([_tv_ttld("Cty A", 50.0), _tv_ttld("Cty B", 50.0)],
                              tien_moi_chunk=1_000_000_000, tong=10_000_000_000)
    v = await SKILL.handler({"thoa_thuan_lien_danh": _TTLD, "bang_gia": trang_dai}, None, {},
                            vision)
    assert v.ket_qua == KET_QUA_DAT                         # 5 tỷ / 10 tỷ = 50% mỗi bên
    assert v.bang_chung.count("5.000.000.000") == 2


async def test_handler_ttld_error_becomes_loi():
    vision = ScriptedVision({})
    v = await SKILL.handler({"thoa_thuan_lien_danh": _TTLD, "bang_gia": _GIA}, None, {}, vision)
    assert v.ket_qua == KET_QUA_LOI


async def test_handler_mot_chunk_bang_gia_loi_thi_ca_verdict_loi():
    """Thiếu 1 chunk là tổng sai -> mọi tỷ lệ sai theo. KHÔNG kết luận trên dữ liệu thiếu."""
    vision = ScriptedVision({
        "[RULE:lien_danh_ttld]": {"thanh_vien": [_tv_ttld("Cty A", 60.0),
                                                 _tv_ttld("Cty B", 40.0)], "trang": [1]},
        # không có kịch bản cho [RULE:lien_danh_bang_gia] -> chunk lỗi
    })
    v = await SKILL.handler({"thoa_thuan_lien_danh": _TTLD, "bang_gia": _GIA}, None, {}, vision)
    assert v.ket_qua == KET_QUA_LOI and "bảng giá" in v.bang_chung
