# backend/experiment/chunking/tests/test_tree.py
from experiment.chunking.schema import (
    Heading, Line, TableRegion, LEVEL_CHUONG, LEVEL_MUC,
)
from experiment.chunking.tree import build_outline, iter_blocks_with_context


def _h(kind, level, number, page, y0=50.0):
    return Heading(kind=kind, level=level, number=number, title=f"{kind} {number}",
                   page=page, y0=y0)


def test_build_outline_nests_muc_under_chuong():
    headings = [_h("chuong", LEVEL_CHUONG, "III", 27),
                _h("muc", LEVEL_MUC, "1", 27, y0=80.0),
                _h("muc", LEVEL_MUC, "2", 28)]
    roots = build_outline(headings)
    assert len(roots) == 1
    assert [c.number for c in roots[0].children] == ["1", "2"]
    assert roots[0].section_path == ["chuong III"]
    assert roots[0].children[0].section_path == ["chuong III", "muc 1"]


def test_build_outline_sets_page_end_from_next_sibling():
    headings = [_h("chuong", LEVEL_CHUONG, "III", 27),
                _h("chuong", LEVEL_CHUONG, "IV", 43)]
    roots = build_outline(headings)
    assert roots[0].page_end == 42  # tới ngay trước Chương IV


def test_iter_blocks_with_context_attaches_deepest_stack():
    headings = [_h("chuong", LEVEL_CHUONG, "III", 27),
                _h("muc", LEVEL_MUC, "1", 27, y0=80.0)]
    body = Line(page=27, text="Giá dự thầu phải cố định", bold=False, size=11.0, y0=120.0, x0=70.0)
    tbl = TableRegion(page=28, y0=60.0, y1=300.0, rows=[["E-CDNT 1.1", "Tên Chủ đầu tư"]])
    results = list(iter_blocks_with_context(headings, [body, tbl]))
    assert len(results) == 2
    body_block, body_stack = results[0]
    assert [h.number for h in body_stack] == ["III", "1"]
    tbl_block, tbl_stack = results[1]
    assert isinstance(tbl_block, TableRegion)
    assert [h.number for h in tbl_stack] == ["III", "1"]
