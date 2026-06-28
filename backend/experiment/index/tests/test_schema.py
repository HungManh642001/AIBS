import uuid

from llama_index.core.schema import MetadataMode

from experiment.index.schema import FAKE_DIM, chunk_to_node, point_id

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
