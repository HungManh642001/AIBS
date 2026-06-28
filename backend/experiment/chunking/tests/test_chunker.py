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
    headings = [_h("chuong", LEVEL_CHUONG, "II", "Chương II. BẢNG DỮ LIỆU", 23)]
    header = ["Mã", "Giá trị"]
    rows = [header] + [[f"E-CDNT {i}", f"giá trị {i}"] for i in range(30)]
    tbl = TableRegion(page=23, y0=60.0, y1=700.0, rows=rows)
    chunks = make_chunks(headings, [], [tbl], doc="hsmt", table_rows_per_group=12)
    groups = [c for c in chunks if c.node_type == "table_row_group"]
    assert len(groups) >= 2
    assert all("Mã" in c.text and "Giá trị" in c.text for c in groups)  # header lặp mỗi nhóm
