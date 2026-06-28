from services.hsmt_locator import locate_hsmt_sections

PAGES = [
    {"page": 1, "text": "Chương I. Bảng dữ liệu đấu thầu. Giá trị bảo đảm dự thầu: 150 triệu"},
    {"page": 2, "text": "Tiếp tục bảng dữ liệu, các mục BDS chi tiết"},
    {"page": 3, "text": "Chương III. Tiêu chuẩn đánh giá về tính hợp lệ"},
    {"page": 4, "text": "Bảng tiêu chí năng lực tiếp theo (vẫn thuộc tiêu chuẩn đánh giá)"},
]


def test_tcdg_is_a_range_to_end():
    out = locate_hsmt_sections(PAGES)
    assert out["tcdg"]["located"] is True
    assert [p["page"] for p in out["tcdg"]["pages"]] == [3, 4]


def test_bds_range_stops_before_next_heading():
    out = locate_hsmt_sections(PAGES)
    assert out["bds"]["located"] is True
    assert [p["page"] for p in out["bds"]["pages"]] == [1, 2]


def test_matches_despite_missing_diacritics():
    pages = [{"page": 1, "text": "CHUONG III. TIEU CHUAN DANH GIA ho so du thau"}]
    out = locate_hsmt_sections(pages)
    assert out["tcdg"]["located"] is True
    assert [p["page"] for p in out["tcdg"]["pages"]] == [1]


def test_not_located_returns_empty_no_fallback():
    pages = [{"page": 1, "text": "không có heading chuẩn nào cả"}]
    out = locate_hsmt_sections(pages)
    assert out["tcdg"]["located"] is False and out["tcdg"]["pages"] == []
    assert out["bds"]["located"] is False and out["bds"]["pages"] == []
