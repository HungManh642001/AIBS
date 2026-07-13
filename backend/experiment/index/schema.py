"""Map chunk dict (chunks.jsonl) -> LlamaIndex TextNode cho vector index."""
from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Any

from llama_index.core.schema import TextNode

COLLECTION = "hsmt_chunks"
FAKE_DIM = 256  # số chiều của DeterministicEmbedding (offline/test)
TEXT_KEY = "text"

# Index bỏ TCĐG (nguồn tiêu chí, đã bóc ở list/analyze qua chuong3_groups.json).
# Biểu mẫu GIỮ LẠI: tiêu chuẩn có thể yêu cầu 'đúng mẫu số N' -> step-3 phải tra được nội dung mẫu;
# nhiễu mẫu-trống với need giá trị được lọc ở phía truy vấn (is_form metadata).
# Phát hiện theo TIÊU ĐỀ (bền hơn số chương: Biểu mẫu có thể Chương IV/V tùy HSMT).
_EXCLUDE_SECTIONS = ("tieu chuan danh gia",)
_FORM_MARK = "bieu mau"
_RE_FORM_ID = re.compile(r"mau\s*(?:so\s*)?(\d+[a-z]?(?:\.\d+)*)")  # chạy trên text đã _norm; giữ số phụ '05c.1'


def _norm(s: str) -> str:
    s = (s or "").lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def keep_for_index(chunk: dict[str, Any]) -> bool:
    """True nếu chunk vào index (mọi chương trừ TCĐG — nguồn tiêu chí, đã bóc riêng)."""
    joined = _norm(" ".join(chunk.get("section_path") or []))
    return not any(x in joined for x in _EXCLUDE_SECTIONS)


def is_form_chunk(chunk: dict[str, Any]) -> bool:
    """True nếu chunk thuộc chương Biểu mẫu (mẫu trống cho nhà thầu điền)."""
    return _FORM_MARK in _norm(" ".join(chunk.get("section_path") or []))


def form_id_of(chunk: dict[str, Any]) -> str:
    """Mã mẫu ('01', '04a', '05c.1') từ section_path/đầu text; '' nếu không thấy."""
    hay = _norm(" ".join([*(chunk.get("section_path") or []), (chunk.get("text") or "")[:160]]))
    m = _RE_FORM_ID.search(hay)
    return m.group(1) if m else ""

# Namespace cố định -> uuid5(chunk_id) ổn định giữa các lần build (upsert idempotent,
# build lại không nhân đôi điểm). Qdrant yêu cầu point id là UUID/int hợp lệ.
_NS = uuid.UUID("a3f1c2d4-5e6b-7a8c-9d0e-1f2a3b4c5d6e")


def point_id(chunk_id: str) -> str:
    """ID điểm Qdrant = uuid5(chunk_id): chuỗi UUID hợp lệ, ổn định theo chunk_id."""
    return str(uuid.uuid5(_NS, chunk_id))


def chunk_to_node(chunk: dict[str, Any]) -> TextNode:
    """chunk dict -> TextNode: chỉ `text` đem embed; mọi field còn lại vào metadata."""
    text = chunk.get(TEXT_KEY, "") or ""
    metadata = {k: v for k, v in chunk.items() if k != TEXT_KEY}
    # Metadata suy diễn cho lọc phía truy vấn: need 'đúng mẫu số N' tra VÀO Biểu mẫu,
    # need giá trị loại Biểu mẫu khỏi lượt tra chung. int 0/1 (MetadataFilter không nhận bool).
    metadata["is_form"] = int(is_form_chunk(chunk))
    metadata["form_id"] = form_id_of(chunk) if metadata["is_form"] else ""
    node = TextNode(text=text, id_=point_id(chunk["chunk_id"]), metadata=metadata)
    # Loại toàn bộ metadata khỏi chuỗi đem embed/LLM -> embedding chỉ phản ánh nội dung chunk.
    keys = list(metadata.keys())
    node.excluded_embed_metadata_keys = keys
    node.excluded_llm_metadata_keys = keys
    return node


def chunks_to_nodes(chunks: list[dict[str, Any]]) -> list[TextNode]:
    """Chuyển danh sách chunk dict thành danh sách TextNode."""
    return [chunk_to_node(c) for c in chunks]
