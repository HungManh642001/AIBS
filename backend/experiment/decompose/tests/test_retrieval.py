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
