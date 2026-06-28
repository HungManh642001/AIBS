"""Map chunk dict (chunks.jsonl) -> LlamaIndex TextNode cho vector index."""
from __future__ import annotations

import uuid
from typing import Any

from llama_index.core.schema import TextNode

COLLECTION = "hsmt_chunks"
FAKE_DIM = 256  # số chiều của DeterministicEmbedding (offline/test)
TEXT_KEY = "text"

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
    node = TextNode(text=text, id_=point_id(chunk["chunk_id"]), metadata=metadata)
    # Loại toàn bộ metadata khỏi chuỗi đem embed/LLM -> embedding chỉ phản ánh nội dung chunk.
    keys = list(metadata.keys())
    node.excluded_embed_metadata_keys = keys
    node.excluded_llm_metadata_keys = keys
    return node


def chunks_to_nodes(chunks: list[dict[str, Any]]) -> list[TextNode]:
    """Chuyển danh sách chunk dict thành danh sách TextNode."""
    return [chunk_to_node(c) for c in chunks]
