from services import artifact_catalog as cat


def test_catalog_has_legality_codes():
    for code in ["don_du_thau", "bao_dam_du_thau", "thoa_thuan_lien_danh", "dang_ky_kinh_doanh"]:
        a = cat.get_artifact(code)
        assert a is not None and a["nhom"] == "hop_le" and a["label"]


def test_dang_ky_kinh_doanh_thay_the_tu_cach_phap_ly():
    """Gọi đúng tên tài liệu thật (ĐKKD) — bỏ hẳn nhãn 'tư cách pháp lý/hợp lệ' mơ hồ."""
    a = cat.get_artifact("dang_ky_kinh_doanh")
    assert a is not None and a["label"] == "Giấy đăng ký kinh doanh"
    assert "tư cách" not in a["label"]
    assert not any("tư cách" in al for al in a["aliases"])
    # `mo_ta` ĐƯỢC nhắc "tư cách" — nhưng chỉ theo nghĩa PHỦ ĐỊNH ("không chọn chỉ vì tiêu chí nói
    # về tư cách"), tức vẫn giữ đúng ý: ĐKKD không phải tài liệu chứng minh tư cách hợp lệ.
    assert "chỉ chọn khi" in a["mo_ta"].lower()
    assert cat.get_artifact("tu_cach_phap_ly") is None
    assert "tu_cach_phap_ly" not in cat.all_codes()
    for raw in ["dang_ky_kinh_doanh", "dkkd", "Đăng ký doanh nghiệp",
                "giấy chứng nhận đăng ký"]:
        assert cat.resolve_code(raw) == "dang_ky_kinh_doanh"


def test_all_codes_includes_other_groups():
    codes = set(cat.all_codes())
    assert {"bao_cao_tai_chinh", "hop_dong_tuong_tu", "bang_gia"} <= codes


def test_match_artifact_by_alias():
    code, conf = cat.match_artifact("Đây là THƯ BẢO LÃNH dự thầu của ngân hàng")
    assert code == "bao_dam_du_thau" and conf > 0


def test_match_artifact_none_when_no_alias():
    code, conf = cat.match_artifact("nội dung không liên quan abcxyz")
    assert code is None and conf == 0.0


def test_resolve_code_snaps_offcatalog_to_canonical():
    # Mã LLM sinh lệch danh mục -> ép về code chuẩn (chống route trượt -> 'thiếu hồ sơ').
    assert cat.resolve_code("bao_lanh_du_thau") == "bao_dam_du_thau"
    assert cat.resolve_code("Bảo lãnh dự thầu") == "bao_dam_du_thau"


def test_resolve_code_keeps_valid_and_rejects_unknown():
    for code in cat.all_codes():
        assert cat.resolve_code(code) == code
    assert cat.resolve_code("xyz_khong_ton_tai") is None
    assert cat.resolve_code("") is None


def test_catalog_has_giay_uy_quyen():
    """Giấy ủy quyền = file riêng trong HSDT — luật chữ ký cần mã này để tìm GUQ khi ký thay."""
    a = cat.get_artifact("giay_uy_quyen")
    assert a is not None and a["nhom"] == "hop_le" and a["label"]
    assert cat.resolve_code("giay_uy_quyen") == "giay_uy_quyen"
    assert cat.resolve_code("Giấy ủy quyền") == "giay_uy_quyen"
    assert cat.resolve_code("văn bản ủy quyền") == "giay_uy_quyen"
    assert cat.la_dung_chung("giay_uy_quyen") is False


def test_catalog_has_webform():
    """webform = kết quả mở thầu (dùng chung cả gói) — decompose cần mã này để khai hsdt_can_kiem_tra."""
    a = cat.get_artifact("webform")
    assert a is not None and a["label"]
    assert cat.resolve_code("webform") == "webform"
    assert cat.resolve_code("Kết quả mở thầu") == "webform"
    assert cat.resolve_code("biên bản mở thầu") == "webform"


def test_webform_is_marked_shared_across_vendors():
    """webform chứa dữ liệu MỌI nhà thầu -> phải đánh dấu để evaluate lọc trước khi đưa vào prompt."""
    assert cat.la_dung_chung("webform") is True
    for code in ["don_du_thau", "bang_gia", "dang_ky_kinh_doanh", "bao_dam_du_thau"]:
        assert cat.la_dung_chung(code) is False      # hồ sơ riêng của nhà thầu
    assert cat.la_dung_chung("khong_ton_tai") is False


def test_webform_aliases_do_not_swallow_existing_codes():
    """resolve_code có fallback substring 2 chiều -> alias mới có thể NUỐT mã cũ. Khoá lại."""
    for code in ["don_du_thau", "bao_dam_du_thau", "thoa_thuan_lien_danh", "dang_ky_kinh_doanh",
                 "bao_cao_tai_chinh", "hop_dong_tuong_tu", "ke_khai_nhan_su", "ke_khai_thiet_bi",
                 "de_xuat_ky_thuat", "catalogue_thong_so", "bang_gia"]:
        assert cat.resolve_code(code) == code
    assert cat.resolve_code("bảng giá") == "bang_gia"          # không bị webform nuốt
    assert cat.resolve_code("thư bảo lãnh") == "bao_dam_du_thau"


def test_mo_ta_la_muc_luc_noi_dung_khong_phai_lap_lai_nhan():
    """`mo_ta` phải nói tài liệu CHỨA GÌ — đó là căn cứ để decompose chọn hồ sơ.

    Mô tả chỉ lặp lại nhãn ("Báo cáo tài chính.") dạy model rằng trường này là nhãn, nó quay về
    suy đoán theo chủ đề của tiêu chí và gán nhầm hồ sơ. Khoá lại bằng 2 dấu hiệu: đủ dài để chứa
    thông tin thật, và không phải chỉ là cái nhãn viết lại.
    """
    for code in cat.all_codes():
        a = cat.get_artifact(code)
        mo_ta = a["mo_ta"]
        assert len(mo_ta) >= 80, f"{code}: mo_ta quá ngắn để nói được tài liệu chứa gì"
        assert mo_ta.strip(". ").lower() != a["label"].lower(), f"{code}: mo_ta chỉ lặp lại label"


def test_don_du_thau_mo_ta_neu_ro_la_noi_nha_thau_tu_khai():
    """Tư cách hợp lệ được nhà thầu TỰ KHAI trong đơn — đây là quy ước nghiệp vụ không suy ra
    được từ nội dung điều khoản, nên phải nằm trong mô tả để bước phân rã chọn đúng hồ sơ."""
    mo_ta = cat.get_artifact("don_du_thau")["mo_ta"].lower()
    assert "tự khai" in mo_ta and "tư cách hợp lệ" in mo_ta


def test_dang_ky_kinh_doanh_mo_ta_chan_suy_doan_theo_chu_de():
    """Chặn đúng lỗi đã gặp: 'tư cách hợp lệ' -> đoán bừa sang giấy đăng ký kinh doanh."""
    assert "chỉ chọn khi" in cat.get_artifact("dang_ky_kinh_doanh")["mo_ta"].lower()


def test_mo_ta_khong_pha_so_khop_ma():
    """`mo_ta` chỉ đi vào prompt — KHÔNG được tham gia _norm_index, kẻo mô tả dài đụng mã khác."""
    for code in cat.all_codes():
        assert cat.resolve_code(code) == code
    assert cat.resolve_code("xyz_khong_ton_tai") is None
