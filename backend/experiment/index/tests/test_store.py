from llama_index.core.schema import TextNode
from qdrant_client import QdrantClient

from experiment.index.schema import point_id
from experiment.index.store import build_index, build_vector_store, hybrid_retriever


def _node(cid: str, text: str, **md) -> TextNode:
    meta = {"chunk_id": cid, **md}
    node = TextNode(text=text, id_=point_id(cid), metadata=meta)
    node.excluded_embed_metadata_keys = list(meta.keys())
    return node


def test_build_and_retrieve(det_embedder):
    client = QdrantClient(location=":memory:")
    store = build_vector_store(client, "t_store")
    nodes = [
        _node("c1", "Bảo đảm dự thầu giá trị và hiệu lực theo HSMT", page_start=27),
        _node("c2", "Doanh thu bình quân ba năm tài chính gần nhất", page_start=40),
        _node("c3", "Phụ lục kỹ thuật phần 4 thông số hàng hóa", page_start=50),
    ]
    index = build_index(nodes, store, det_embedder)

    assert client.count("t_store").count == 3

    hits = hybrid_retriever(index, k=3).retrieve("bảo đảm dự thầu")
    assert hits
    assert hits[0].node.metadata["chunk_id"] == "c1"
    assert hits[0].node.metadata["page_start"] == 27
