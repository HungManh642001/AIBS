"""Nhánh LIÊN DANH của luật chữ ký đơn dự thầu: neo vào THỎA THUẬN LIÊN DANH, không phải ĐKKD."""
from experiment.evaluate.rules.chu_ky_khop_dkkd import (
    ChuKyLech, doi_chieu_chu_ky_lien_danh, ket_luan_uy_quyen_lien_danh,
)
from experiment.evaluate.schema import KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_SOI

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
