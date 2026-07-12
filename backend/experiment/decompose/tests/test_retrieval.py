def test_index_retriever_returns_hits(memory_retriever):
    hits = memory_retriever("bảo đảm dự thầu giá trị", k=3)
    assert hits
    top = hits[0]
    assert "text" in top and "metadata" in top and "score" in top
    # BM25 thật: chunk nói về bảo đảm dự thầu nổi lên đầu.
    assert top["metadata"]["chunk_id"] == "d1"


def test_index_retriever_technical_query(memory_retriever):
    hits = memory_retriever("yêu cầu kỹ thuật thông số phần 4", k=3)
    assert hits[0]["metadata"]["chunk_id"] == "d2"


def test_index_retriever_clause_doc_filter(memory_retriever):
    """Lọc clause_doc='bdl' -> CHỈ trả chunk E-BDL (loại chunk kỹ thuật/E-CDNT dù trùng từ khoá)."""
    hits = memory_retriever("thông số kỹ thuật phần 4", k=5, clause_doc="bdl")
    assert hits  # vẫn có kết quả (trong tập E-BDL)
    ids = {h["metadata"]["chunk_id"] for h in hits}
    assert ids <= {"d1", "d3"}      # d1,d3 là bdl
    assert "d2" not in ids          # d2 (cdnt) bị loại dù query nhắm kỹ thuật


def test_index_retriever_is_form_filter():
    """Lọc is_form=True -> CHỈ trả chunk Biểu mẫu (need 'đúng mẫu số N' tra vào mẫu).

    Index riêng (không dùng fixture chung): DeterministicEmbedding là hash nên thêm node
    vào fixture chung sẽ xáo thứ hạng các test cũ.
    """
    from llama_index.core.schema import TextNode
    from qdrant_client import QdrantClient

    from experiment.decompose.retrieval import IndexRetriever
    from experiment.index.embedder import DeterministicEmbedding
    from experiment.index.schema import point_id
    from experiment.index.store import build_index, build_vector_store

    client = QdrantClient(location=":memory:")
    store = build_vector_store(client, "t_form_filter")
    nodes = []
    for cid, text, is_form in [
        ("f1", "Mẫu số 01 ĐƠN DỰ THẦU kính gửi bên mời thầu", 1),
        ("f2", "Đơn dự thầu phải có chữ ký người đại diện", 0),
    ]:
        n = TextNode(text=text, id_=point_id(cid), metadata={"chunk_id": cid, "is_form": is_form})
        n.excluded_embed_metadata_keys = ["chunk_id", "is_form"]
        nodes.append(n)
    retriever = IndexRetriever(build_index(nodes, store, DeterministicEmbedding()))

    hits = retriever("mẫu đơn dự thầu", k=5, is_form=True)
    assert hits
    assert {h["metadata"]["chunk_id"] for h in hits} == {"f1"}


def test_index_retriever_source_doc_filter():
    """Lọc source_doc='tbmt' -> CHỈ chunk TBMT (route theo nguồn tài liệu).

    Index riêng (không dùng fixture chung): DeterministicEmbedding là hash nên thêm node
    vào fixture chung sẽ xáo thứ hạng các test cũ.
    """
    from llama_index.core.schema import TextNode
    from qdrant_client import QdrantClient

    from experiment.decompose.retrieval import IndexRetriever
    from experiment.index.embedder import DeterministicEmbedding
    from experiment.index.schema import point_id
    from experiment.index.store import build_index, build_vector_store

    client = QdrantClient(location=":memory:")
    store = build_vector_store(client, "t_source_filter")
    nodes = []
    for cid, text, src in [
        ("t1", "Thời điểm đóng thầu 09 giờ 00 ngày 20/6/2025", "tbmt"),
        ("t2", "Nhà thầu nộp bảo đảm dự thầu trước thời điểm đóng thầu", "hsmt"),
    ]:
        n = TextNode(text=text, id_=point_id(cid), metadata={"chunk_id": cid, "source_doc": src})
        n.excluded_embed_metadata_keys = ["chunk_id", "source_doc"]
        nodes.append(n)
    retriever = IndexRetriever(build_index(nodes, store, DeterministicEmbedding()))

    hits = retriever("thời điểm đóng thầu", k=5, source_doc="tbmt")
    assert hits
    assert {h["metadata"]["chunk_id"] for h in hits} == {"t1"}
