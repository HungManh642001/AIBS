# backend/experiment/extract/tests/test_sections.py
from experiment.extract.sections import build_chuong3_groups


def test_four_main_groups_extracted(sample_pdf):
    page, groups = build_chuong3_groups(sample_pdf)
    labels = [g.group for g in groups]
    assert labels == ["hop_le", "nang_luc", "ky_thuat", "tai_chinh"]
    assert page[0] == 27  # Chương III bắt đầu trang 27


def test_nang_luc_keeps_table_rows(sample_pdf):
    _, groups = build_chuong3_groups(sample_pdf)
    nl = next(g for g in groups if g.group == "nang_luc")
    tables = [b for b in nl.blocks if b.type == "table"]
    assert tables, "nhóm năng lực phải có ít nhất 1 block bảng"
    # giữ nguyên rows: có hàng dữ liệu mở đầu bằng TT '1'
    all_rows = [r for t in tables for r in (t.rows or [])]
    assert any(r and r[0].strip() == "1" for r in all_rows)


def test_ky_thuat_is_reference_to_phan_4(sample_pdf):
    _, groups = build_chuong3_groups(sample_pdf)
    kt = next(g for g in groups if g.group == "ky_thuat")
    assert kt.is_reference is True
    assert kt.ref_target == {"kind": "phan", "number": "4"}


def test_hop_le_and_tai_chinh_have_text(sample_pdf):
    _, groups = build_chuong3_groups(sample_pdf)
    hl = next(g for g in groups if g.group == "hop_le")
    tc = next(g for g in groups if g.group == "tai_chinh")
    hl_text = " ".join(b.text or "" for b in hl.blocks)
    tc_text = " ".join(b.text or "" for b in tc.blocks)
    assert "hợp lệ" in hl_text
    assert "thấp nhất" in tc_text  # phương pháp giá thấp nhất
