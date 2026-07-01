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
