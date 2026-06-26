from services.hsmt_locator import locate_hsmt_sections

PAGES = [
    {"page": 1, "text": "Chương I. Bảng dữ liệu đấu thầu. Giá trị bảo đảm dự thầu: 150 triệu"},
    {"page": 2, "text": "Nội dung khác không liên quan"},
    {"page": 3, "text": "Chương III. Tiêu chuẩn đánh giá về tính hợp lệ"},
]


def test_locates_tcdg_and_bds():
    out = locate_hsmt_sections(PAGES)
    assert [p["page"] for p in out["tcdg"]] == [3]
    assert [p["page"] for p in out["bds"]] == [1]


def test_fallback_when_section_missing():
    pages = [{"page": 1, "text": "không có heading chuẩn nào cả"}]
    out = locate_hsmt_sections(pages)
    # fallback: cả hai nhóm = toàn bộ trang
    assert out["tcdg"] == pages and out["bds"] == pages
