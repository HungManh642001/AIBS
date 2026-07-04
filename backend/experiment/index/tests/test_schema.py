import uuid

from llama_index.core.schema import MetadataMode

from experiment.index.schema import FAKE_DIM, chunk_to_node, keep_for_index, point_id

_CHUNK = {
    "chunk_id": "E-HSMT-0042",
    "doc": "E-HSMT",
    "text": "Nội dung tiêu chuẩn",
    "section_path": ["Chương III"],
    "chapter_no": 3,
    "section_title": "TIÊU CHUẨN ĐÁNH GIÁ",
    "level": 2,
    "heading_number": "1",
    "page_start": 27,
    "page_end": 27,
    "node_type": "text",
    "group_hint": "hop_le",
    "char_len": 19,
    "overlap_prev": 0,
}


def test_point_id_stable_and_idempotent():
    a = point_id("E-HSMT-0042")
    assert a == point_id("E-HSMT-0042")  # ổn định giữa các lần gọi
    uuid.UUID(a)  # là UUID hợp lệ (Qdrant yêu cầu)
    assert point_id("E-HSMT-0001") != point_id("E-HSMT-0002")


def test_chunk_to_node_text_and_metadata():
    node = chunk_to_node(_CHUNK)
    assert node.text == "Nội dung tiêu chuẩn"
    assert node.id_ == point_id("E-HSMT-0042")
    assert "text" not in node.metadata
    assert node.metadata["chunk_id"] == "E-HSMT-0042"
    assert node.metadata["group_hint"] == "hop_le"


def test_embed_exclusion_covers_all_metadata():
    node = chunk_to_node(_CHUNK)
    assert set(node.excluded_embed_metadata_keys) == set(node.metadata.keys())
    # Chuỗi đem embed chỉ là text chunk, không lẫn metadata.
    assert node.get_content(metadata_mode=MetadataMode.EMBED) == "Nội dung tiêu chuẩn"


def test_fake_dim_constant():
    assert FAKE_DIM == 256


def _c(path):
    return {"chunk_id": "x", "text": "nội dung", "section_path": path}


def test_keep_for_index_drops_only_tcdg():
    """Index bỏ TCĐG (nguồn tiêu chí, đã bóc riêng); GIỮ Biểu mẫu (tiêu chuẩn có thể yêu cầu
    'đúng mẫu số N' -> step-3 phải tra được nội dung mẫu)."""
    assert not keep_for_index(_c(["PHẦN 4", "Chương III. TIÊU CHUẨN ĐÁNH GIÁ E-HSDT"]))
    assert keep_for_index(_c(["PHẦN 4", "Chương IV. BIỂU MẪU MỜI THẦU VÀ DỰ THẦU"]))
    assert keep_for_index(_c(["Chương V. BIỂU MẪU"]))
    # Giữ: E-BDL, E-CDNT, Yêu cầu kỹ thuật.
    assert keep_for_index(_c(["PHẦN 4", "Chương II. BẢNG DỮ LIỆU ĐẤU THẦU"]))
    assert keep_for_index(_c(["PHẦN 4", "Chương I. CHỈ DẪN NHÀ THẦU"]))
    assert keep_for_index(_c(["PHẦN 4", "Yêu cầu kỹ thuật"]))
    # "Tiêu chí đánh giá kỹ thuật" (chí ≠ chuẩn) -> KHÔNG bị bỏ nhầm.
    assert keep_for_index(_c(["PHẦN 4", "Tiêu chí đánh giá kỹ thuật"]))


def test_chunk_to_node_tags_form_metadata():
    """Chunk Biểu mẫu được gắn is_form + form_id (để retrieve lọc theo need)."""
    form = _c(["Chương IV. BIỂU MẪU MỜI THẦU VÀ DỰ THẦU"])
    form["text"] = "Mẫu số 01. ĐƠN DỰ THẦU\nKính gửi: ..."
    node = chunk_to_node(form)
    assert node.metadata["is_form"] is True and node.metadata["form_id"] == "01"
    # metadata suy diễn cũng bị loại khỏi chuỗi embed như mọi metadata khác
    assert "is_form" in node.excluded_embed_metadata_keys

    normal = _c(["PHẦN 4", "Chương I. CHỈ DẪN NHÀ THẦU"])
    node2 = chunk_to_node(normal)
    assert node2.metadata["is_form"] is False and node2.metadata["form_id"] == ""
