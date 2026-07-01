# backend/experiment/decompose/tests/conftest.py
import json
from pathlib import Path

import pytest
from llama_index.core.schema import TextNode
from qdrant_client import QdrantClient

from experiment.decompose.retrieval import IndexRetriever
from experiment.index.embedder import DeterministicEmbedding
from experiment.index.schema import point_id
from experiment.index.store import build_index, build_vector_store

_OUT_DIR = Path(__file__).resolve().parents[1].parent / "out"


@pytest.fixture
def sample_groups():
    """out/chuong3_groups.json (artefact bước extract). Skip nếu chưa chạy extract."""
    path = _OUT_DIR / "chuong3_groups.json"
    if not path.exists():
        pytest.skip("Không có out/chuong3_groups.json — chạy bước extract trước")
    return {"path": str(path), "data": json.loads(path.read_text(encoding="utf-8"))}


@pytest.fixture
def memory_retriever():
    """retrieve_fn thật trên index in-memory (BM25 + DeterministicEmbedding), offline."""
    client = QdrantClient(location=":memory:")
    store = build_vector_store(client, "t_decompose")
    nodes = []
    for cid, text, clause_doc in [
        ("d1", "Bảo đảm dự thầu giá trị 150 triệu đồng hiệu lực 120 ngày theo BDS", "bdl"),
        ("d2", "Yêu cầu kỹ thuật thông số hàng hóa phần 4 phụ lục", "cdnt"),
        ("d3", "Doanh thu bình quân ba năm tài chính", "bdl"),
    ]:
        n = TextNode(text=text, id_=point_id(cid), metadata={"chunk_id": cid, "clause_doc": clause_doc})
        n.excluded_embed_metadata_keys = ["chunk_id", "clause_doc"]
        nodes.append(n)
    index = build_index(nodes, store, DeterministicEmbedding())
    return IndexRetriever(index)
