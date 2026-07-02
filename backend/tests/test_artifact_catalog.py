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
