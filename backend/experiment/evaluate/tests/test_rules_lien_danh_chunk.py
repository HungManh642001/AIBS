"""Bảng giá dài: chia chunk theo trang + cộng dồn ở code (không cắt mất hạng mục).

Bản thật 15 trang = 68k ký tự, cap cũ 6000 chỉ nuốt 9% -> tổng sai -> tỷ lệ sai. Hai hàm thuần
dưới đây là chỗ giữ tính đúng đắn, test không cần proxy.
"""
from experiment.evaluate.rules.lien_danh_phan_cong import chia_chunk_theo_trang, gop_bang_gia
from experiment.evaluate.schema import PageRecord


def _p(trang, text):
    return PageRecord(file="bg.pdf", trang=trang, loai_ho_so="bang_gia", text=text)


# ---- chia_chunk_theo_trang ----

def test_ngan_gon_thi_mot_chunk():
    chunks = chia_chunk_theo_trang([_p(1, "a" * 100), _p(2, "b" * 100)], 6000)
    assert len(chunks) == 1
    assert "a" * 100 in chunks[0] and "b" * 100 in chunks[0]


def test_gom_trang_cho_toi_khi_day_ngan_sach():
    chunks = chia_chunk_theo_trang([_p(i, "x" * 2000) for i in range(1, 6)], 5000)
    assert len(chunks) == 3          # 2 trang + 2 trang + 1 trang
    assert all(len(c) < 7000 for c in chunks)


def test_khong_bao_gio_cat_giua_trang():
    """Trang dài hơn ngân sách vẫn đi NGUYÊN VẸN — thà 1 call to còn hơn mất dữ liệu."""
    dai = "y" * 20000
    chunks = chia_chunk_theo_trang([_p(1, dai)], 6000)
    assert len(chunks) == 1 and chunks[0].count("y") == 20000


def test_trang_qua_dai_dung_rieng_mot_chunk():
    chunks = chia_chunk_theo_trang([_p(1, "a" * 100), _p(2, "b" * 20000), _p(3, "c" * 100)], 6000)
    assert len(chunks) == 3
    assert chunks[1].count("b") == 20000


def test_khong_co_trang_thi_khong_co_chunk():
    assert chia_chunk_theo_trang([], 6000) == []


def test_chunk_co_so_trang_de_truy_bang_chung():
    chunks = chia_chunk_theo_trang([_p(7, "abc")], 6000)
    assert "[Trang 7]" in chunks[0]


# ---- gop_bang_gia ----

_TV = [{"ten": "Cty A", "neu_ro_hang_muc": True, "mo_ta_cong_viec": "máy chủ", "ty_le_khai": 60.0},
       {"ten": "Cty B", "neu_ro_hang_muc": True, "mo_ta_cong_viec": "UPS", "ty_le_khai": 40.0}]


def _hm(ten, tien, tv):
    return {"stt": "1", "ten": ten, "thanh_tien": tien, "thanh_vien": tv}


def test_cong_don_tien_theo_thanh_vien_qua_nhieu_chunk():
    """Hạng mục của một thành viên nằm rải nhiều trang -> phải cộng dồn, không ghi đè."""
    chunks = [{"hang_muc": [_hm("Máy chủ", 4_000_000_000, "Cty A")], "dong_tong": []},
              {"hang_muc": [_hm("Switch", 2_000_000_000, "Cty A"),
                            _hm("UPS", 4_000_000_000, "Cty B")],
               "dong_tong": [{"nhan": "Tổng cộng", "gia_tri": 10_000_000_000}]}]
    d = gop_bang_gia(_TV, chunks)
    assert d["tong_gia_tri_lien_danh"] == 10_000_000_000
    tv = {t["ten"]: t for t in d["thanh_vien"]}
    assert tv["Cty A"]["tong_tien"] == 6_000_000_000
    assert tv["Cty B"]["tong_tien"] == 4_000_000_000
    assert tv["Cty A"]["ty_le_khai"] == 60.0            # giữ nguyên số khai ở TTLĐ
    assert [h["ten"] for h in tv["Cty A"]["hang_muc"]] == ["Máy chủ", "Switch"]


def test_dong_tong_nhom_khong_bi_tinh_thanh_hang_muc():
    """Bẫy trong bảng thật: 'I. Hàng hóa/dịch vụ liên quan = 20.620.102.120' là TỔNG NHÓM.

    Nó nằm ở dong_tong nên KHÔNG được cộng vào tiền thành viên (nếu không sẽ cộng đôi).
    """
    chunks = [{"hang_muc": [_hm("Máy chủ", 6_000_000_000, "Cty A"),
                            _hm("UPS", 4_000_000_000, "Cty B")],
               "dong_tong": [{"nhan": "I. Hàng hóa/dịch vụ liên quan", "gia_tri": 10_000_000_000},
                             {"nhan": "Tổng cộng", "gia_tri": 10_000_000_000}]}]
    d = gop_bang_gia(_TV, chunks)
    assert sum(t["tong_tien"] for t in d["thanh_vien"]) == 10_000_000_000
    assert d["tong_gia_tri_lien_danh"] == 10_000_000_000


def test_khong_co_dong_tong_thi_lay_tong_hang_muc():
    chunks = [{"hang_muc": [_hm("Máy chủ", 6_000_000_000, "Cty A"),
                            _hm("UPS", 4_000_000_000, "Cty B")], "dong_tong": []}]
    d = gop_bang_gia(_TV, chunks)
    assert d["tong_gia_tri_lien_danh"] == 10_000_000_000
    assert "không có dòng tổng" in d["ghi_chu"]


def test_hang_muc_chua_phan_cong_duoc_bao_cao():
    """Hạng mục không gán được thành viên -> báo ra để guard 'còn hạng mục chưa phân công' bắt."""
    chunks = [{"hang_muc": [_hm("Máy chủ", 6_000_000_000, "Cty A"),
                            _hm("Phụ kiện lạ", 1_000_000_000, "")],
               "dong_tong": [{"nhan": "Tổng cộng", "gia_tri": 7_000_000_000}]}]
    d = gop_bang_gia(_TV, chunks)
    assert d["tien_chua_phan_cong"] == 1_000_000_000


def test_thanh_vien_khong_neu_ro_giu_nguyen_khong_cong_tien():
    tv = [{"ten": "Cty A", "neu_ro_hang_muc": True, "mo_ta_cong_viec": "máy chủ",
           "ty_le_khai": 60.0},
          {"ten": "Cty B", "neu_ro_hang_muc": False, "mo_ta_cong_viec": "cung cấp hàng hóa",
           "ty_le_khai": 40.0}]
    d = gop_bang_gia(tv, [{"hang_muc": [_hm("Máy chủ", 6_000_000_000, "Cty A")],
                           "dong_tong": []}])
    mo_ho = next(t for t in d["thanh_vien"] if t["ten"] == "Cty B")
    assert mo_ho["neu_ro_hang_muc"] is False and mo_ho["tong_tien"] == 0.0


def test_ten_thanh_vien_lech_hoa_thuong_van_khop():
    """LLM trả 'CTY A' còn TTLĐ ghi 'Cty A' -> vẫn phải cộng đúng người."""
    chunks = [{"hang_muc": [_hm("Máy chủ", 6_000_000_000, "  CTY A ")], "dong_tong": []}]
    d = gop_bang_gia(_TV, chunks)
    tv = {t["ten"]: t for t in d["thanh_vien"]}
    assert tv["Cty A"]["tong_tien"] == 6_000_000_000
    assert d["tien_chua_phan_cong"] == 0.0
