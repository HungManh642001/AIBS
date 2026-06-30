from experiment.chunking.schema import Heading, Line, TableRegion, LEVEL_CHUONG, LEVEL_MUC
from experiment.chunking.chunker import group_hint, split_text, make_chunks


def _h(kind, level, number, title, page, y0=50.0):
    return Heading(kind=kind, level=level, number=number, title=title, page=page, y0=y0)


def test_group_hint_maps_muc_titles():
    assert group_hint([_h("muc", LEVEL_MUC, "1", "Mục 1. Đánh giá tính hợp lệ", 27)]) == "hop_le"
    assert group_hint([_h("muc", LEVEL_MUC, "2", "Mục 2. năng lực và kinh nghiệm", 28)]) == "nang_luc"
    assert group_hint([_h("muc", LEVEL_MUC, "3", "Mục 3. về kỹ thuật", 40)]) == "ky_thuat"
    assert group_hint([_h("muc", LEVEL_MUC, "4", "Mục 4. về tài chính", 40)]) == "tai_chinh"
    assert group_hint([]) == "unknown"


def test_split_text_respects_budget_and_overlap():
    text = "x" * 4000
    parts = split_text(text, max_chars=1800, overlap=180)
    assert all(len(p) <= 1800 for p, _ in parts)
    assert parts[0][1] == 0 and parts[1][1] == 180  # overlap_prev


def test_make_chunks_text_section_carries_section_path():
    headings = [_h("chuong", LEVEL_CHUONG, "III", "Chương III. TIÊU CHUẨN", 27),
                _h("muc", LEVEL_MUC, "1", "Mục 1. Đánh giá tính hợp lệ", 27, y0=80.0)]
    body = [Line(page=27, text="Giá dự thầu phải cố định bằng số.", bold=False,
                 size=11.0, y0=120.0, x0=70.0)]
    chunks = make_chunks(headings, body, [], doc="hsmt")
    assert chunks and chunks[0].node_type == "text"
    assert chunks[0].chapter_no == "III"
    assert chunks[0].group_hint == "hop_le"
    assert chunks[0].section_path == ["Chương III. TIÊU CHUẨN", "Mục 1. Đánh giá tính hợp lệ"]


def test_make_chunks_large_table_splits_into_row_groups_with_header():
    # Bảng thường (KHÔNG phải E-BDL/E-CDNT) -> vẫn nhóm hàng, lặp header.
    headings = [_h("chuong", LEVEL_CHUONG, "III", "Chương III. TIÊU CHUẨN ĐÁNH GIÁ", 30)]
    header = ["Mã", "Giá trị"]
    rows = [header] + [[f"TT {i}", f"giá trị {i}"] for i in range(30)]
    tbl = TableRegion(page=30, y0=60.0, y1=700.0, rows=rows)
    chunks = make_chunks(headings, [], [tbl], doc="hsmt", table_rows_per_group=12)
    groups = [c for c in chunks if c.node_type == "table_row_group"]
    assert len(groups) >= 2
    assert all("Mã" in c.text and "Giá trị" in c.text for c in groups)  # header lặp mỗi nhóm


def test_make_chunks_clause_chapter_splits_per_row():
    """E-BDL/E-CDNT -> mỗi hàng = 1 chunk 'clause' kèm clause_id (KHÔNG gói nhiều điều khoản)."""
    # E-BDL: col0 = "E-CDNT <id>"
    bdl_heading = [_h("chuong", LEVEL_CHUONG, "II", "Chương II. BẢNG DỮ LIỆU ĐẤU THẦU", 23)]
    bdl_rows = [["E-CDNT 18.2", "Giá trị bảo đảm dự thầu: 6.100.000 VNĐ"],
                ["E-CDNT 17.1", "Thời hạn hiệu lực E-HSDT: ≥ 90 ngày"]]
    tbl = TableRegion(page=23, y0=60.0, y1=700.0, rows=bdl_rows)
    chunks = make_chunks(bdl_heading, [], [tbl], doc="hsmt", table_rows_per_group=12)
    assert len(chunks) == 2 and all(c.node_type == "clause" for c in chunks)
    assert [c.clause_id for c in chunks] == ["18.2", "17.1"]
    assert all(c.clause_doc == "bdl" for c in chunks)
    assert "6.100.000" in chunks[0].text

    # E-CDNT: col0 = "<id>. Tiêu đề"
    cdnt_heading = [_h("chuong", LEVEL_CHUONG, "I", "Chương I. CHỈ DẪN NHÀ THẦU", 5)]
    cdnt_rows = [["4. Hành vi bị\ncấm", "4.1. Đưa, nhận hối lộ; 4.2. ..."]]
    tbl2 = TableRegion(page=5, y0=60.0, y1=200.0, rows=cdnt_rows)
    c2 = make_chunks(cdnt_heading, [], [tbl2], doc="hsmt")
    assert c2[0].node_type == "clause" and c2[0].clause_id == "4" and c2[0].clause_doc == "cdnt"
