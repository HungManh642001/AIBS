# backend/experiment/chunking/tests/test_layout_tables.py
from experiment.chunking.layout import extract_lines, extract_tables


def test_bds_table_has_ecdnt_codes(sample_pdf):
    lines = extract_lines(sample_pdf)
    tables, _ = extract_tables(sample_pdf, lines)
    # Bảng BDS (Chương II ~ trang 23-26) là bảng 2 cột [mã E-CDNT, giá trị]
    bds = [t for t in tables if 23 <= t.page <= 26]
    assert bds, "phải phát hiện bảng BDS quanh trang 23-26"
    codes = [r[0] for t in bds for r in t.rows if r and r[0]]
    assert any("E-CDNT" in (c or "") for c in codes)


def test_lines_inside_table_are_dropped(sample_pdf):
    lines = extract_lines(sample_pdf)
    _, kept = extract_tables(sample_pdf, lines)
    assert len(kept) < len(lines)  # đã loại bớt dòng nằm trong bảng
