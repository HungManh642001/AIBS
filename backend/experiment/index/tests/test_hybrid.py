from llama_index.core.schema import TextNode
from qdrant_client import QdrantClient

from experiment.index.schema import point_id
from experiment.index.store import build_index, build_vector_store, hybrid_retriever


def _node(cid: str, text: str) -> TextNode:
    node = TextNode(text=text, id_=point_id(cid), metadata={"chunk_id": cid})
    node.excluded_embed_metadata_keys = ["chunk_id"]
    return node


def test_keyword_match_ranks_top(det_embedder):
    """BM25 (sparse, thật) kéo node khớp keyword lên top dù dense là vector xác định."""
    client = QdrantClient(location=":memory:")
    store = build_vector_store(client, "t_hybrid")
    nodes = [
        _node("k1", "Tiêu chuẩn đánh giá về kỹ thuật và phụ lục phần 4"),
        _node("k2", "Đánh giá tính hợp lệ của hồ sơ dự thầu"),
        _node("k3", "Phương pháp giá thấp nhất về tài chính"),
    ]
    index = build_index(nodes, store, det_embedder)

    hits = hybrid_retriever(index, k=3).retrieve("phụ lục kỹ thuật phần 4")
    assert hits[0].node.metadata["chunk_id"] == "k1"
