"""Nhánh LIÊN DANH của luật chữ ký đơn dự thầu: neo vào THỎA THUẬN LIÊN DANH, không phải ĐKKD."""
from experiment.evaluate.rules.chu_ky_khop_dkkd import (
    SKILL, SYS_RULE_LIEN_DANH_KY, ChuKyLech, doi_chieu_chu_ky_lien_danh,
    ket_luan_uy_quyen_lien_danh, lien_danh_ky_prompt,
)
from experiment.evaluate.schema import (
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_LOI, KET_QUA_SOI, KET_QUA_THIEU, PageRecord,
)
from experiment.evaluate.vision import ScriptedVision

_OSB = "CÔNG TY CỔ PHẦN TẬP ĐOÀN OSB"
_OHT = "CÔNG TY TNHH CÔNG NGHỆ CAO OSB"


def _tv(ten, dai_dien, dung_dau=False):
    return {"ten_phap_nhan": ten, "nguoi_dai_dien": dai_dien, "la_dung_dau": dung_dau}


def _ck(phap_nhan, nguoi_ky, thanh_vien_ttld=""):
    return {"phap_nhan": phap_nhan, "nguoi_ky": nguoi_ky,
            "thanh_vien_ttld": thanh_vien_ttld or phap_nhan}


def test_dung_dau_ky_thay_mat_lien_danh_dung_nguoi_thi_dat():
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường")],
        "chu_ky": [_ck(_OSB, "Nguyễn Hồng Sơn")]})
    assert kq == KET_QUA_DAT and lech == []
    assert "đứng đầu" in gc and "Nguyễn Hồng Sơn" in bc


def test_tat_ca_thanh_vien_cung_ky_dung_nguoi_thi_dat():
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường")],
        "chu_ky": [_ck(_OSB, "Nguyễn Hồng Sơn"), _ck(_OHT, "Trần Vũ Thường")]})
    assert kq == KET_QUA_DAT and lech == []
    assert "tất cả thành viên" in gc


def test_ky_mot_phan_thi_khong_dat_va_neu_ten_thanh_vien_thieu():
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường"),
                       _tv("CÔNG TY ABC", "Lê Văn C")],
        "chu_ky": [_ck(_OSB, "Nguyễn Hồng Sơn"), _ck(_OHT, "Trần Vũ Thường")]})
    assert kq == KET_QUA_KHONG and lech == []
    assert "CÔNG TY ABC" in gc


def test_chi_thanh_vien_khong_dung_dau_ky_thi_khong_dat():
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường")],
        "chu_ky": [_ck(_OHT, "Trần Vũ Thường")]})
    assert kq == KET_QUA_KHONG and lech == []
    assert "đứng đầu" in gc


def test_phap_nhan_ky_khong_co_trong_ttld_thi_khong_dat():
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True)],
        "chu_ky": [{"phap_nhan": "CÔNG TY LẠ", "nguoi_ky": "X", "thanh_vien_ttld": ""}]})
    assert kq == KET_QUA_KHONG and "CÔNG TY LẠ" in gc


def test_llm_bo_trong_thanh_vien_ttld_van_khop_khi_ten_chuan_hoa_bang_nhau():
    """Guard MỘT CHIỀU: LLM không gán thì code tự so tên chuẩn hoá (hoa/thường/dấu)."""
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv("Công ty cổ phần Tập đoàn OSB", "Nguyễn Hồng Sơn", dung_dau=True)],
        "chu_ky": [{"phap_nhan": "CÔNG TY CỔ PHẦN TẬP ĐOÀN OSB", "nguoi_ky": "Nguyễn Hồng Sơn",
                    "thanh_vien_ttld": ""}]})
    assert kq == KET_QUA_DAT


def test_nguoi_ky_lech_dai_dien_thi_chua_ket_luan_va_tra_ve_lech():
    """Ca OSB gói 54: đơn đứng tên thành viên đứng đầu nhưng người ký là đại diện thành viên kia."""
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường")],
        "chu_ky": [_ck(_OSB, "Trần Vũ Thường")]})
    assert kq == ""                                  # CHƯA kết luận -> phải xét ủy quyền
    assert lech == [ChuKyLech(phap_nhan=_OSB, nguoi_ky="Trần Vũ Thường",
                              nguoi_dai_dien="Nguyễn Hồng Sơn")]


def test_thieu_can_cu_thi_soi_khong_doan():
    assert doi_chieu_chu_ky_lien_danh({"thanh_vien": [], "chu_ky": [_ck(_OSB, "A")]})[0] == KET_QUA_SOI
    assert doi_chieu_chu_ky_lien_danh(
        {"thanh_vien": [_tv(_OSB, "A", dung_dau=True)], "chu_ky": []})[0] == KET_QUA_SOI
    # không đọc được tên người ký
    assert doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "A", dung_dau=True)],
        "chu_ky": [_ck(_OSB, "")]})[0] == KET_QUA_SOI
    # TTLD không nêu thành viên đứng đầu, mà cũng không phải mọi thành viên cùng ký
    assert doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "A"), _tv(_OHT, "B")],
        "chu_ky": [_ck(_OSB, "A")]})[0] == KET_QUA_SOI


def _muc(phap_nhan, **kw):
    m = {"phap_nhan": phap_nhan, "nguoi_uy_quyen": "Nguyễn Hồng Sơn",
         "nguoi_duoc_uy_quyen": "Trần Vũ Thường", "phap_nhan_uy_quyen": phap_nhan,
         "phap_nhan_khop": True, "dung_nguoi": True, "dung_pham_vi": True, "ghi_chu": ""}
    m.update(kw)
    return m


_LECH = [ChuKyLech(phap_nhan=_OSB, nguoi_ky="Trần Vũ Thường",
                   nguoi_dai_dien="Nguyễn Hồng Sơn")]


def test_uy_quyen_du_ba_dieu_kien_thi_dat():
    assert ket_luan_uy_quyen_lien_danh(_LECH, [_muc(_OSB)]) == (KET_QUA_DAT, "")


def test_uy_quyen_tu_phap_nhan_khac_thi_khong_dat():
    """Ca OSB gói 54: GUQ do thành viên KHÁC (không phải thành viên đứng tên khối chữ ký) cấp."""
    kq, gc = ket_luan_uy_quyen_lien_danh(
        _LECH, [_muc(_OSB, phap_nhan_uy_quyen=_OHT, phap_nhan_khop=False)])
    assert kq == KET_QUA_KHONG and _OHT in gc and "vô hiệu" in gc


def test_khong_co_muc_uy_quyen_cho_chu_ky_lech_thi_khong_dat():
    kq, gc = ket_luan_uy_quyen_lien_danh(_LECH, [])
    assert kq == KET_QUA_KHONG and "không có giấy ủy quyền" in gc


def test_sai_nguoi_hoac_sai_pham_vi_thi_khong_dat():
    kq1, gc1 = ket_luan_uy_quyen_lien_danh(
        _LECH, [_muc(_OSB, dung_nguoi=False, nguoi_duoc_uy_quyen="Lê Văn X")])
    assert kq1 == KET_QUA_KHONG and "Lê Văn X" in gc1
    kq2, gc2 = ket_luan_uy_quyen_lien_danh(_LECH, [_muc(_OSB, dung_pham_vi=False)])
    assert kq2 == KET_QUA_KHONG and "phạm vi" in gc2


def test_khong_doc_duoc_ten_ben_uy_quyen_thi_soi():
    kq, gc = ket_luan_uy_quyen_lien_danh(_LECH, [_muc(_OSB, phap_nhan_uy_quyen="")])
    assert kq == KET_QUA_SOI and "không đọc được" in gc


# --- Review Task 5 (finding 1): tên pháp nhân KHÔNG ĐỌC ĐƯỢC phải SOI, không đoán 'không đạt' ---

def test_khoi_chu_ky_khong_ro_ten_phap_nhan_thi_soi_khong_ket_luan_khong_dat():
    """Khác ca 'pháp nhân lạ' (có tên, chỉ là không có trong TTLD): đây THIẾU CĂN CỨ hoàn toàn —
    cả `phap_nhan` lẫn `thanh_vien_ttld` đều rỗng, không có gì để tra cứu."""
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường")],
        "chu_ky": [{"phap_nhan": "", "nguoi_ky": "X", "thanh_vien_ttld": ""}]})
    assert kq == KET_QUA_SOI and lech == []
    assert "không đọc được" in gc


# --- Review Task 5 (finding 2): NHIỀU thành viên cùng gắn cờ đứng đầu -> SOI, không chọn bừa ---

def test_hai_thanh_vien_cung_dung_dau_ma_chi_mot_nguoi_ky_thi_soi():
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True),
                       _tv(_OHT, "Trần Vũ Thường", dung_dau=True)],
        "chu_ky": [_ck(_OSB, "Nguyễn Hồng Sơn")]})
    assert kq == KET_QUA_SOI and lech == []
    assert "nhiều hơn một" in gc.lower()


def test_hinh_thuc_b_van_dat_du_co_nhieu_co_dung_dau():
    """Guard 'nhiều cờ đứng đầu' KHÔNG được chặn nhầm hình thức B — hình thức B không cần biết
    ai đứng đầu, chỉ cần MỌI thành viên cùng ký."""
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True),
                       _tv(_OHT, "Trần Vũ Thường", dung_dau=True)],
        "chu_ky": [_ck(_OSB, "Nguyễn Hồng Sơn"), _ck(_OHT, "Trần Vũ Thường")]})
    assert kq == KET_QUA_DAT and lech == []
    assert "tất cả thành viên" in gc


# --- Review Task 5 (finding 3): ket_luan_uy_quyen_lien_danh với NHIỀU chữ ký lệch (chưa test) ---

_LECH2 = [ChuKyLech(phap_nhan=_OSB, nguoi_ky="Trần Vũ Thường", nguoi_dai_dien="Nguyễn Hồng Sơn"),
          ChuKyLech(phap_nhan=_OHT, nguoi_ky="Lê Văn C", nguoi_dai_dien="Phạm Thị D")]


def test_uy_quyen_hai_thanh_vien_deu_du_dieu_kien_thi_dat():
    assert ket_luan_uy_quyen_lien_danh(_LECH2, [_muc(_OSB), _muc(_OHT)]) == (KET_QUA_DAT, "")


def test_uy_quyen_mot_dung_mot_sai_phap_nhan_thi_khong_dat_va_neu_dung_ten():
    """Chỉ nêu tên thành viên SAI trong ghi_chu — thành viên hợp lệ không bị nêu nhầm."""
    kq, gc = ket_luan_uy_quyen_lien_danh(
        _LECH2, [_muc(_OSB), _muc(_OHT, phap_nhan_uy_quyen=_OSB, phap_nhan_khop=False)])
    assert kq == KET_QUA_KHONG
    assert gc.startswith(_OHT) and "vô hiệu" in gc
    assert "; " not in gc     # chỉ MỘT lỗi — không lẫn thông điệp của thành viên OSB hợp lệ


def test_uy_quyen_mot_loi_mot_soi_thi_uu_tien_khong_dat():
    """MỘT chữ ký lệch có GUQ vô hiệu (loi) + MỘT chữ ký lệch khác thiếu tên bên ủy quyền (soi)
    -> loi PHẢI thắng soi, kết quả chung là KHÔNG ĐẠT."""
    kq, gc = ket_luan_uy_quyen_lien_danh(
        _LECH2, [_muc(_OSB, phap_nhan_uy_quyen=_OHT, phap_nhan_khop=False),
                 _muc(_OHT, phap_nhan_uy_quyen="")])
    assert kq == KET_QUA_KHONG
    assert _OSB in gc and "vô hiệu" in gc


# --- Task 6: prompt bóc dữ liệu + rẽ nhánh trong handler ---

def _p(trang, loai, text):
    return PageRecord(file="f.pdf", trang=trang, loai_ho_so=loai, text=text)


_BT_LD = {
    "don_du_thau": [_p(1, "don_du_thau", "ĐẠI DIỆN HỢP PHÁP CỦA NHÀ THẦU LIÊN DANH ...")],
    "thoa_thuan_lien_danh": [_p(1, "thoa_thuan_lien_danh", "Thành viên đứng đầu: ...")],
}


def test_prompt_lien_danh_co_marker_va_ca_hai_tai_lieu():
    p = lien_danh_ky_prompt("ĐƠN: ký bởi Trần Vũ Thường", "TTLD: đứng đầu là Tập đoàn OSB")
    assert "[RULE:chu_ky_lien_danh]" in p
    assert "ĐƠN: ký bởi Trần Vũ Thường" in p and "TTLD: đứng đầu là Tập đoàn OSB" in p
    assert "KHÔNG bịa" in SYS_RULE_LIEN_DANH_KY
    assert "thanh_vien_ttld" in SYS_RULE_LIEN_DANH_KY


async def test_co_ttld_thi_KHONG_doc_dkkd():
    """MẤU CHỐT: có thỏa thuận liên danh -> neo vào TTLD, tuyệt đối không đụng ĐKKD."""
    by_type = dict(_BT_LD, dang_ky_kinh_doanh=[_p(1, "dang_ky_kinh_doanh", "đại diện: Lê Văn X")])
    v = ScriptedVision({"[RULE:chu_ky_lien_danh]": {
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường")],
        "chu_ky": [_ck(_OSB, "Nguyễn Hồng Sơn")], "trang": [1], "do_tin": 0.9}})
    verdict = await SKILL.handler(by_type, None, {}, v)
    assert verdict.ket_qua == KET_QUA_DAT
    assert verdict.noi_dung_kiem_tra == "Người ký đơn dự thầu đúng đại diện liên danh (thỏa thuận liên danh)"
    assert verdict.nguon_doc == ["don_du_thau", "thoa_thuan_lien_danh"]
    assert len(v.calls) == 1                                  # 1 call duy nhất
    assert "[RULE:chu_ky_khop_dkkd]" not in v.calls[0][0]     # KHÔNG hề gọi nhánh ĐKKD
    assert v.calls[0][1] == 0                                 # text-only, không đính ảnh


async def test_khong_co_ttld_thi_giu_nhanh_dkkd_cu():
    """Hồi quy: nhà thầu độc lập vẫn đi nhánh ĐKKD như trước."""
    by_type = {
        "don_du_thau": [_p(1, "don_du_thau", "Người ký: Nguyễn Văn A")],
        "dang_ky_kinh_doanh": [_p(1, "dang_ky_kinh_doanh", "đại diện: Nguyễn Văn A")],
    }
    v = ScriptedVision({"[RULE:chu_ky_khop_dkkd]": {
        "ket_qua": "đạt", "nguoi_ky": "Nguyễn Văn A", "dai_dien_phap_luat": "Nguyễn Văn A",
        "nha_thau_don": "Công ty ABC", "doanh_nghiep_dkkd": "Công ty ABC", "phap_nhan_khop": True}})
    verdict = await SKILL.handler(by_type, None, {}, v)
    assert verdict.ket_qua == KET_QUA_DAT
    assert verdict.nguon_doc == ["don_du_thau", "dang_ky_kinh_doanh"]


async def test_thieu_don_du_thau_van_thieu_ho_so_du_co_ttld():
    v = ScriptedVision({})
    verdict = await SKILL.handler({"thoa_thuan_lien_danh": _BT_LD["thoa_thuan_lien_danh"]},
                                  None, {}, v)
    assert verdict.ket_qua == KET_QUA_THIEU and v.calls == []


async def test_ai_loi_thi_verdict_loi_khong_bia():
    v = ScriptedVision({"[RULE:chu_ky_lien_danh]": RuntimeError("proxy hỏng")})
    verdict = await SKILL.handler(_BT_LD, None, {}, v)
    assert verdict.ket_qua == KET_QUA_LOI and "proxy hỏng" in verdict.bang_chung


async def test_ky_mot_phan_ra_khong_dat_chi_mot_call():
    v = ScriptedVision({"[RULE:chu_ky_lien_danh]": {
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường")],
        "chu_ky": [_ck(_OHT, "Trần Vũ Thường")], "trang": [1]}})
    verdict = await SKILL.handler(_BT_LD, None, {}, v)
    assert verdict.ket_qua == KET_QUA_KHONG and len(v.calls) == 1


# --- Task 7: bước 2 thẩm định giấy ủy quyền ---

_KB_LECH = {"[RULE:chu_ky_lien_danh]": {
    "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường")],
    "chu_ky": [_ck(_OSB, "Trần Vũ Thường")], "trang": [1], "do_tin": 0.9}}


async def test_ca_that_goi_54_uy_quyen_tu_thanh_vien_khac_thi_khong_dat():
    """Ca OSB gói 54: đơn đứng tên OSB Tập đoàn, người ký là đại diện OSB Công nghệ cao,
    giấy ủy quyền lại do OSB Công nghệ cao cấp -> ủy quyền vô hiệu."""
    by_type = dict(_BT_LD, giay_uy_quyen=[_p(1, "giay_uy_quyen", "Nguyễn Hồng Sơn ủy quyền ...")])
    v = ScriptedVision({**_KB_LECH, "[RULE:chu_ky_lien_danh_uy_quyen]": {
        "muc": [{"phap_nhan": _OSB, "nguoi_uy_quyen": "Nguyễn Hồng Sơn",
                 "nguoi_duoc_uy_quyen": "Trần Vũ Thường", "phap_nhan_uy_quyen": _OHT,
                 "phap_nhan_khop": False, "dung_nguoi": True, "dung_pham_vi": True}],
        "bang_chung": "Giấy ủy quyền trang 1", "trang": [1], "do_tin": 0.95}})
    verdict = await SKILL.handler(by_type, None, {}, v)
    assert verdict.ket_qua == KET_QUA_KHONG
    assert "vô hiệu" in verdict.ghi_chu and _OHT in verdict.ghi_chu
    assert verdict.nguon_doc == ["don_du_thau", "thoa_thuan_lien_danh", "giay_uy_quyen"]
    assert len(v.calls) == 2


async def test_uy_quyen_hop_le_tu_dung_thanh_vien_thi_dat():
    by_type = dict(_BT_LD, giay_uy_quyen=[_p(1, "giay_uy_quyen", "ủy quyền ...")])
    v = ScriptedVision({**_KB_LECH, "[RULE:chu_ky_lien_danh_uy_quyen]": {
        "muc": [{"phap_nhan": _OSB, "nguoi_uy_quyen": "Nguyễn Hồng Sơn",
                 "nguoi_duoc_uy_quyen": "Trần Vũ Thường", "phap_nhan_uy_quyen": _OSB,
                 "phap_nhan_khop": True, "dung_nguoi": True, "dung_pham_vi": True}],
        "bang_chung": "Giấy ủy quyền trang 1", "trang": [1]}})
    verdict = await SKILL.handler(by_type, None, {}, v)
    assert verdict.ket_qua == KET_QUA_DAT and len(v.calls) == 2


async def test_ky_lech_ma_khong_co_giay_uy_quyen_thi_khong_dat_khong_goi_llm_lan_2():
    v = ScriptedVision(dict(_KB_LECH))
    verdict = await SKILL.handler(_BT_LD, None, {}, v)
    assert verdict.ket_qua == KET_QUA_KHONG
    assert len(v.calls) == 1                              # KHÔNG gọi LLM lần 2
    assert "không có giấy ủy quyền" in verdict.ghi_chu
    assert verdict.nguon_doc == ["don_du_thau", "thoa_thuan_lien_danh"]


def test_prompt_uy_quyen_lien_danh_neu_ro_tung_khoi_chu_ky():
    from experiment.evaluate.rules.chu_ky_khop_dkkd import (
        SYS_RULE_UY_QUYEN_LIEN_DANH, uy_quyen_lien_danh_prompt,
    )

    p = uy_quyen_lien_danh_prompt("GUQ: nội dung ủy quyền", _LECH)
    assert "[RULE:chu_ky_lien_danh_uy_quyen]" in p
    assert _OSB in p and "Trần Vũ Thường" in p and "Nguyễn Hồng Sơn" in p
    assert "GUQ: nội dung ủy quyền" in p
    assert "dung_pham_vi" in SYS_RULE_UY_QUYEN_LIEN_DANH
    assert "KHÔNG bịa" in SYS_RULE_UY_QUYEN_LIEN_DANH


def test_guard_phap_nhan_mot_chieu_trong_nhanh_uy_quyen():
    """LLM nói 'khác pháp nhân' mà hai tên chuẩn hoá giống hệt -> tin CODE, tránh báo động giả."""
    kq, gc = ket_luan_uy_quyen_lien_danh(
        _LECH, [_muc(_OSB, phap_nhan_uy_quyen=_OSB.lower(), phap_nhan_khop=False)])
    assert kq == KET_QUA_DAT and gc == ""


# --- Fix wave, finding 1: verdict phải giữ CẢ suy diễn LẪN trích dẫn nguyên văn của LLM ---

async def test_verdict_lien_danh_giu_ca_suy_dien_va_trich_dan_nguyen_van():
    """`bang_chung` phải TRÍCH ĐƯỢC: chuỗi suy diễn (kết luận có cấu trúc) đứng trước, nguyên văn
    tài liệu do LLM trích đứng sau. Bỏ một trong hai là chuyên gia mất câu gốc để đối chiếu."""
    trich = "Đơn tr.3: 'ĐẠI DIỆN HỢP PHÁP CỦA NHÀ THẦU LIÊN DANH — Nguyễn Hồng Sơn'; TTLD tr.2"
    v = ScriptedVision({"[RULE:chu_ky_lien_danh]": {
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường")],
        "chu_ky": [_ck(_OSB, "Nguyễn Hồng Sơn")],
        "bang_chung": trich, "trang": [3], "do_tin": 0.9}})
    verdict = await SKILL.handler(_BT_LD, None, {}, v)
    assert verdict.ket_qua == KET_QUA_DAT
    assert "thỏa thuận liên danh ghi đại diện là" in verdict.bang_chung   # chuỗi suy diễn
    assert trich in verdict.bang_chung                                    # nguyên văn LLM trích
    assert verdict.bang_chung.index("thỏa thuận") < verdict.bang_chung.index(trich)


async def test_verdict_lien_danh_khong_lap_dau_cham_phay_khi_llm_khong_trich():
    """LLM để `bang_chung` rỗng -> chỉ còn chuỗi suy diễn, không dính dấu phân cách thừa."""
    v = ScriptedVision({"[RULE:chu_ky_lien_danh]": {
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True)],
        "chu_ky": [_ck(_OSB, "Nguyễn Hồng Sơn")], "bang_chung": "", "trang": [1]}})
    verdict = await SKILL.handler(_BT_LD, None, {}, v)
    assert verdict.ket_qua == KET_QUA_DAT
    assert not verdict.bang_chung.endswith("; ") and "; ;" not in verdict.bang_chung


# --- Fix wave, finding 2: so TÊN NGƯỜI phải chuẩn hoá xưng hô + khoảng trắng ---

def test_norm_ten_nguoi_bo_xung_ho_va_gop_khoang_trang():
    from experiment.evaluate.rules.chu_ky_khop_dkkd import _norm_ten_nguoi

    goc = _norm_ten_nguoi("Nguyễn Hồng Sơn")
    assert _norm_ten_nguoi("Ông Nguyễn Hồng Sơn") == goc
    assert _norm_ten_nguoi("Bà  Nguyễn   Hồng Sơn") == goc     # gộp khoảng trắng + bỏ 'Bà'
    assert _norm_ten_nguoi("Nguyễn  Hồng   Sơn") == goc
    assert _norm_ten_nguoi("  NGUYỄN HỒNG SƠN  ") == goc
    assert _norm_ten_nguoi("Mr. Nguyễn Hồng Sơn") == goc
    assert _norm_ten_nguoi("Trần Vũ Thường") != goc            # tên THẬT SỰ khác vẫn khác


def test_ttld_ghi_xung_ho_ong_ma_don_khong_ghi_thi_van_dat():
    """TTLD (bảng scan) hay ghi 'Ông Nguyễn Hồng Sơn', đơn chỉ ghi tên — KHÔNG được coi là lệch."""
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Ông Nguyễn Hồng Sơn", dung_dau=True)],
        "chu_ky": [_ck(_OSB, "Nguyễn Hồng Sơn")]})
    assert kq == KET_QUA_DAT and lech == []


def test_ocr_chen_double_space_hoac_lech_hoa_thuong_van_dat():
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True)],
        "chu_ky": [_ck(_OSB, "NGUYỄN  HỒNG SƠN")]})
    assert kq == KET_QUA_DAT and lech == []


def test_ten_nguoi_that_su_khac_van_phai_ra_lech_khong_bi_nuot():
    """Nới lỏng tới mức nuốt mất phát hiện thật thì luật vô dụng — ca lệch người vẫn phải lệch."""
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Ông Nguyễn Hồng Sơn", dung_dau=True),
                       _tv(_OHT, "Trần Vũ Thường")],
        "chu_ky": [_ck(_OSB, "Trần Vũ Thường")]})
    assert kq == "" and len(lech) == 1
    assert lech[0].nguoi_ky == "Trần Vũ Thường"


# --- Fix wave, finding 3: LLM bỏ trống `thanh_vien_ttld` -> tên viết tắt đi chung nhánh 'lạ' ---

def test_ten_viet_tat_ma_llm_bo_trong_thanh_vien_ttld_van_ra_khong_dat():
    """ĐÁNH ĐỔI CÓ CHỦ ĐÍCH (chủ dự án quyết) — test này là TÀI LIỆU SỐNG của quyết định đó.

    Ca spec dòng 293-294: đơn ghi tắt 'Cty CP Tập đoàn OSB', TTLD ghi đầy đủ 'Công ty cổ phần Tập
    đoàn OSB'. Khi LLM bỏ trống `thanh_vien_ttld`, code chỉ còn phép so chuỗi chuẩn hoá TUYỆT ĐỐI
    nên KHÔNG phân biệt được 'viết tắt cùng một pháp nhân' với 'pháp nhân lạ ký đơn liên danh'.
    Đứng trước hai lựa chọn không phân biệt được, hệ thống GIỮ PHÁT HIỆN THẬT -> 'không đạt'.

    Đường xử lý ĐÚNG cho tên viết tắt không nằm ở đây mà ở khoá `thanh_vien_ttld`:
    `SYS_RULE_LIEN_DANH_KY` bắt LLM chép đúng ten_phap_nhan của thành viên mà khối chữ ký thuộc về,
    và `_tra_thanh_vien` thử khoá đó TRƯỚC `phap_nhan` —
    `test_tra_thanh_vien_uu_tien_thanh_vien_ttld_hon_phap_nhan` là chỗ khoá đường đó lại.
    Nhánh này chỉ với tới khi LLM bỏ trống CẢ HAI khoá, tức dữ liệu bóc đã hỏng.
    """
    kq, bc, gc, lech = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv("Công ty cổ phần Tập đoàn OSB", "Nguyễn Hồng Sơn", dung_dau=True)],
        "chu_ky": [{"phap_nhan": "Cty CP Tập đoàn OSB", "nguoi_ky": "Nguyễn Hồng Sơn",
                    "thanh_vien_ttld": ""}]})
    assert kq == KET_QUA_KHONG and lech == []
    assert "Cty CP Tập đoàn OSB" in gc                       # nêu đúng tên đọc được trên đơn
    assert "Cty CP Tập đoàn OSB" in bc and "Nguyễn Hồng Sơn" in bc   # bằng chứng vẫn trích được


def test_ca_khong_ro_ten_phap_nhan_khong_bi_gop_vao_nhanh_phap_nhan_la():
    """Hai ca KHÁC hẳn nhau: 'không đọc được tên' -> SOI (thiếu căn cứ, không được quy kết bằng một
    cái tên rỗng); 'đọc được tên nhưng không có trong TTLD' -> 'không đạt'."""
    kq_mo_ho, _, gc_mo_ho, _ = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True)],
        "chu_ky": [{"phap_nhan": "", "nguoi_ky": "X", "thanh_vien_ttld": ""}]})
    kq_la, _, gc_la, _ = doi_chieu_chu_ky_lien_danh({
        "thanh_vien": [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True)],
        "chu_ky": [{"phap_nhan": "CÔNG TY LẠ", "nguoi_ky": "X", "thanh_vien_ttld": ""}]})
    assert kq_mo_ho == KET_QUA_SOI and kq_la == KET_QUA_KHONG
    assert "không đọc được" in gc_mo_ho and "không đọc được" not in gc_la
    assert gc_mo_ho != gc_la


def test_tra_thanh_vien_uu_tien_thanh_vien_ttld_hon_phap_nhan():
    """Hai khoá trỏ về HAI thành viên khác nhau -> phần gán của LLM (`thanh_vien_ttld`) thắng."""
    from experiment.evaluate.rules.chu_ky_khop_dkkd import _tra_thanh_vien

    tvs = [_tv(_OSB, "Nguyễn Hồng Sơn", dung_dau=True), _tv(_OHT, "Trần Vũ Thường")]
    tv = _tra_thanh_vien(tvs, {"phap_nhan": _OHT, "nguoi_ky": "X", "thanh_vien_ttld": _OSB})
    assert tv is not None and tv["ten_phap_nhan"] == _OSB
