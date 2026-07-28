"""Đối chiếu điều kiện áp dụng theo giá trị — TẤT ĐỊNH, 0 call LLM."""
from experiment.decompose.dieu_kien import doi_chieu_tieu_chi, parse_so, tim_gia_tri
from experiment.decompose.schema import KET_LUAN_AP_DUNG, KET_LUAN_KHONG_AP_DUNG


# ---- parse số ----
def test_parse_so_dau_cham_la_phan_cach_nghin():
    assert parse_so("939.000.000 VND") == 939_000_000
    assert parse_so("50.000.000") == 50_000_000


def test_parse_so_boi_so_tieng_viet():
    assert parse_so("50 triệu đồng") == 50_000_000
    assert parse_so("1,5 tỷ") == 1_500_000_000
    assert parse_so("200 nghìn") == 200_000


def test_parse_so_dau_cham_khong_phai_nghin_thi_la_thap_phan():
    """'1.5' không phải nhóm 3 chữ số -> thập phân, KHÔNG phải 15."""
    assert parse_so("1.5 tỷ") == 1_500_000_000


def test_parse_so_khong_co_so_tra_none():
    assert parse_so("không có con số nào") is None
    assert parse_so("") is None


# ---- tìm giá trị đại lượng ----
def test_tim_gia_tri_lay_so_cung_dong_va_giu_nguyen_van_co_dau():
    got = tim_gia_tri("giá trị bảo đảm dự thầu",
                      [("nd khác", "Giá trị bảo đảm dự thầu: 939.000.000 VND")])
    assert [v for v, _ in got] == [939_000_000]
    assert "939.000.000" in got[0][1] and "Giá trị bảo đảm dự thầu" in got[0][1]


def test_tim_gia_tri_bo_dau_van_khop():
    """Khớp trên bản bỏ dấu -> lệch dấu/OCR vẫn tìm ra."""
    assert tim_gia_tri("GIA TRI BAO DAM DU THAU",
                       [("x", "Giá trị bảo đảm dự thầu: 939.000.000 VND")])[0][0] == 939_000_000


def test_tim_gia_tri_khong_vo_lay_so_dong_khac():
    """Số phải NẰM CÙNG DÒNG với tên đại lượng, không vơ số của dòng dưới."""
    assert tim_gia_tri("giá trị bảo đảm dự thầu",
                       [("x", "Giá trị bảo đảm dự thầu: chưa nêu\nThời hạn: 150 ngày")]) == []


# ---- đối chiếu cả tiêu chí ----
def _nd(ten, **kw):
    nd = {"noi_dung_kiem_tra": ten, "yeu_cau": "theo HSMT", "thong_tin_bo_sung": "",
          "dieu_kien_ap_dung": {}}
    nd.update(kw)
    return nd


def _crit(*nds):
    return {"noi_dung_can_kiem_tra": list(nds)}


def _dk(nguong="50 triệu đồng", phep="<", dai_luong="giá trị bảo đảm dự thầu"):
    return {"dai_luong": dai_luong, "phep_so_sanh": phep, "nguong": nguong}


def test_dieu_kien_khong_thoa_thi_khong_ap_dung():
    """Ca thật gói 54: HSMT quy định 939 triệu, nội dung chỉ áp dụng khi < 50 triệu -> N/A."""
    gia = _nd("Giá trị bảo lãnh", thong_tin_bo_sung="Giá trị bảo đảm dự thầu: 939.000.000 VND")
    cam_ket = _nd("Cam kết trong đơn dự thầu", dieu_kien_ap_dung=_dk())
    crit = _crit(gia, cam_ket)

    assert doi_chieu_tieu_chi(crit) == 1
    assert cam_ket["dieu_kien_ap_dung"]["ket_luan"] == KET_LUAN_KHONG_AP_DUNG
    can_cu = cam_ket["dieu_kien_ap_dung"]["can_cu"]
    assert "939,000,000" in can_cu and "KHÔNG THOẢ" in can_cu   # căn cứ kiểm chứng được
    assert gia["dieu_kien_ap_dung"] == {}                        # nội dung không có điều kiện: không đụng


def test_dieu_kien_thoa_thi_van_cham():
    gia = _nd("Giá trị bảo lãnh", thong_tin_bo_sung="Giá trị bảo đảm dự thầu: 30.000.000 VND")
    cam_ket = _nd("Cam kết trong đơn dự thầu", dieu_kien_ap_dung=_dk())

    assert doi_chieu_tieu_chi(_crit(gia, cam_ket)) == 0
    assert cam_ket["dieu_kien_ap_dung"]["ket_luan"] == KET_LUAN_AP_DUNG


def test_khong_tra_duoc_dai_luong_thi_van_cham():
    """FAIL-SAFE: không tìm ra đại lượng -> KHÔNG kết luận, nội dung vẫn được chấm."""
    cam_ket = _nd("Cam kết trong đơn dự thầu", dieu_kien_ap_dung=_dk())

    assert doi_chieu_tieu_chi(_crit(_nd("nội dung khác"), cam_ket)) == 0
    assert cam_ket["dieu_kien_ap_dung"]["ket_luan"] == ""
    assert "không tra được" in cam_ket["dieu_kien_ap_dung"]["can_cu"]


def test_nguon_mau_thuan_thi_khong_doan():
    """Hai nơi ra hai giá trị khác nhau -> KHÔNG chọn bừa, vẫn chấm."""
    a = _nd("A", thong_tin_bo_sung="Giá trị bảo đảm dự thầu: 939.000.000 VND")
    b = _nd("B", thong_tin_bo_sung="Giá trị bảo đảm dự thầu: 20.000.000 VND")
    cam_ket = _nd("Cam kết", dieu_kien_ap_dung=_dk())

    assert doi_chieu_tieu_chi(_crit(a, b, cam_ket)) == 0
    assert cam_ket["dieu_kien_ap_dung"]["ket_luan"] == ""
    assert "nhiều giá trị khác nhau" in cam_ket["dieu_kien_ap_dung"]["can_cu"]


def test_khong_tu_khop_nguong_cua_chinh_no():
    """`yeu_cau` của chính nội dung chứa 'nhỏ hơn 50 triệu' — KHÔNG được lấy đó làm giá trị."""
    cam_ket = _nd("Cam kết",
                  yeu_cau="Áp dụng khi giá trị bảo đảm dự thầu nhỏ hơn 50 triệu đồng",
                  thong_tin_bo_sung="Giá trị bảo đảm dự thầu nhỏ hơn 50 triệu đồng thì cam kết",
                  dieu_kien_ap_dung=_dk())

    assert doi_chieu_tieu_chi(_crit(cam_ket)) == 0
    assert cam_ket["dieu_kien_ap_dung"]["ket_luan"] == ""


def test_lay_duoc_gia_tri_tu_bang_neo():
    cam_ket = _nd("Cam kết", dieu_kien_ap_dung=_dk(dai_luong="giá gói thầu", nguong="1 tỷ"))
    anchors = {"giá gói thầu": {"gia_tri": "2.500.000.000 VND", "nguon": "A-BDL"}}

    assert doi_chieu_tieu_chi(_crit(cam_ket), anchors) == 1
    assert cam_ket["dieu_kien_ap_dung"]["ket_luan"] == KET_LUAN_KHONG_AP_DUNG


def test_phep_so_sanh_la_khong_doc_duoc_thi_van_cham():
    cam_ket = _nd("Cam kết", dieu_kien_ap_dung=_dk(phep="nhỏ hơn"))
    gia = _nd("Giá", thong_tin_bo_sung="Giá trị bảo đảm dự thầu: 939.000.000 VND")

    assert doi_chieu_tieu_chi(_crit(gia, cam_ket)) == 0
    assert "không đọc được điều kiện" in cam_ket["dieu_kien_ap_dung"]["can_cu"]


def test_khong_co_dieu_kien_thi_khong_dung_gi():
    nd = _nd("Bình thường")
    assert doi_chieu_tieu_chi(_crit(nd)) == 0
    assert nd["dieu_kien_ap_dung"] == {}
