from experiment.chunking.schema import Line
from experiment.chunking.layout import extract_lines, _strip_furniture


def _mk(page, text, y0=100.0):
    return Line(page=page, text=text, bold=False, size=11.0, y0=y0, x0=70.0)


def test_strip_removes_repeating_page_furniture():
    # "Trang N" và mã biểu lặp ở mọi trang -> rác, phải bỏ
    lines = []
    for p in range(1, 6):
        lines.append(_mk(p, "VSP-000-TM-238/BM-03", y0=20.0))
        lines.append(_mk(p, f"Trang {p + 28}", y0=820.0))
        lines.append(_mk(p, f"Nội dung thực trang {p}", y0=400.0))
    kept = _strip_furniture(lines, n_pages=5)
    texts = [l.text for l in kept]
    assert all("VSP-000-TM-238" not in t for t in texts)
    assert all(not t.startswith("Trang ") for t in texts)
    assert any("Nội dung thực" in t for t in texts)


def test_strip_keeps_unique_body_lines():
    lines = [_mk(1, "Chương III. TIÊU CHUẨN ĐÁNH GIÁ"), _mk(2, "Mục 1. Đánh giá tính hợp lệ")]
    kept = _strip_furniture(lines, n_pages=2)
    assert len(kept) == 2


def test_extract_lines_reads_chuong_iii_heading(sample_pdf):
    lines = extract_lines(sample_pdf)
    bold_texts = [l.text for l in lines if l.bold]
    assert any("TIÊU CHUẨN ĐÁNH GIÁ" in t for t in bold_texts)
    # heading Chương III thật nằm ~trang 27 (không phải mục lục trang 2-3)
    hits = [l.page for l in lines if "TIÊU CHUẨN ĐÁNH GIÁ E-HSDT" in l.text and l.bold]
    assert 27 in hits
