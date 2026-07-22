from services import artifact_catalog as cat


def test_catalog_has_legality_codes():
    for code in ["don_du_thau", "bao_dam_du_thau", "thoa_thuan_lien_danh", "tu_cach_phap_ly"]:
        a = cat.get_artifact(code)
        assert a is not None and a["nhom"] == "hop_le" and a["label"]


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
    for code in ["don_du_thau", "bang_gia", "tu_cach_phap_ly", "bao_dam_du_thau"]:
        assert cat.la_dung_chung(code) is False      # hồ sơ riêng của nhà thầu
    assert cat.la_dung_chung("khong_ton_tai") is False


def test_webform_aliases_do_not_swallow_existing_codes():
    """resolve_code có fallback substring 2 chiều -> alias mới có thể NUỐT mã cũ. Khoá lại."""
    for code in ["don_du_thau", "bao_dam_du_thau", "thoa_thuan_lien_danh", "tu_cach_phap_ly",
                 "bao_cao_tai_chinh", "hop_dong_tuong_tu", "ke_khai_nhan_su", "ke_khai_thiet_bi",
                 "de_xuat_ky_thuat", "catalogue_thong_so", "bang_gia"]:
        assert cat.resolve_code(code) == code
    assert cat.resolve_code("bảng giá") == "bang_gia"          # không bị webform nuốt
    assert cat.resolve_code("thư bảo lãnh") == "bao_dam_du_thau"
