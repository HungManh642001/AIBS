import json
from experiment.chunking.schema import (
    Line, TableRegion, Heading, OutlineNode, Chunk,
    chunks_to_jsonl, outline_to_json,
    LEVEL_PHAN, LEVEL_CHUONG, LEVEL_MUC, LEVEL_DIEU,
)


def test_levels_are_ordered():
    assert (LEVEL_PHAN, LEVEL_CHUONG, LEVEL_MUC, LEVEL_DIEU) == (0, 1, 2, 3)


def test_chunks_to_jsonl_roundtrip_preserves_unicode():
    c = Chunk(
        chunk_id="c1", doc="hsmt", text="Tiêu chuẩn đánh giá",
        section_path=["Chương III. TIÊU CHUẨN"], chapter_no="III",
        section_title="Mục 1", level=LEVEL_MUC, heading_number="1",
        page_start=27, page_end=27, node_type="text",
        group_hint="hop_le", char_len=19, overlap_prev=0,
    )
    line = chunks_to_jsonl([c])
    parsed = json.loads(line)
    assert parsed["text"] == "Tiêu chuẩn đánh giá"
    assert parsed["group_hint"] == "hop_le"
    assert "\\u" not in line  # ensure_ascii=False giữ nguyên tiếng Việt


def test_outline_to_json_nests_children():
    child = OutlineNode(level=LEVEL_MUC, kind="muc", number="1", title="Mục 1",
                        page_start=27, page_end=39, section_path=["Chương III", "Mục 1"],
                        children=[])
    root = OutlineNode(level=LEVEL_CHUONG, kind="chuong", number="III", title="Chương III",
                       page_start=27, page_end=42, section_path=["Chương III"], children=[child])
    data = json.loads(outline_to_json([root]))
    assert data[0]["children"][0]["title"] == "Mục 1"
