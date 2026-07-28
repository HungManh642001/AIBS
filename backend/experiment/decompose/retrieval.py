"""Cổng truy hồi cho workflow phân rã.

Thật: truy hồi hybrid trên index Qdrant on-disk (`experiment.index`). Test: tiêm in-memory
hoặc scripted. retrieve_fn(query, k) -> list[{text, metadata, score}].
"""
from __future__ import annotations

import threading
from typing import Any, Callable

from qdrant_client import QdrantClient
from llama_index.core.vector_stores import FilterOperator, MetadataFilter, MetadataFilters

from experiment.index.embedder import build_embedder
from experiment.index.schema import COLLECTION
from experiment.index.store import build_bm25, build_vector_store, hybrid_retriever, open_index

# retrieve_fn(query, k) -> list[hit dict]
RetrieveFn = Callable[..., list[dict[str, Any]]]


def hits_to_dicts(hits: Any) -> list[dict[str, Any]]:
    return [
        {"text": h.node.text or "", "metadata": h.node.metadata or {}, "score": float(h.score or 0.0)}
        for h in hits
    ]


class IndexRetriever:
    """retrieve_fn dựa trên một VectorStoreIndex đã mở.

    Cache BM25 theo (k, bộ lọc): dựng BM25 tốn 85ms còn truy vấn chỉ 0.9ms, mà `__call__` chạy
    một lần cho MỖI need. Bộ lọc và k chỉ nhận vài tổ hợp nên cache nhỏ và không bao giờ nở ra.
    Có Lock vì workflow gọi retrieve qua asyncio.to_thread -> nhiều thread cùng vào.
    """

    def __init__(self, nodes: Any, index: Any):
        self.nodes = nodes
        self._index = index
        self._bm25: dict[tuple[Any, ...], Any] = {}
        self._khoa = threading.Lock()

    def _bm25_cho(self, khoa: tuple[Any, ...], filters: Any, k: int) -> Any:
        with self._khoa:
            r = self._bm25.get(khoa)
            if r is None:
                r = build_bm25(self.nodes, filters, k)
                self._bm25[khoa] = r
            return r

    def __call__(self, query: str, k: int = 5, clause_doc: str | None = None,
                 is_form: bool | None = None, source_doc: str | None = None) -> list[dict[str, Any]]:
        conds = []
        if clause_doc:
            conds.append(MetadataFilter(key="clause_doc", value=clause_doc, operator=FilterOperator.EQ))
        if is_form is not None:  # need 'đúng mẫu số N' -> tra VÀO chunk Biểu mẫu (payload int 0/1)
            conds.append(MetadataFilter(key="is_form", value=int(is_form), operator=FilterOperator.EQ))
        if source_doc:  # rout theo nguồn tài liệu (hsmt/tbmt/...)
            conds.append(MetadataFilter(key="source_doc", value=source_doc, operator=FilterOperator.EQ))
        filters = MetadataFilters(filters=conds) if conds else None
        # Khoá dựng từ CHÍNH các tham số sinh ra filters — chính xác và rẻ hơn băm MetadataFilters.
        bm25 = self._bm25_cho((k, clause_doc, is_form, source_doc), filters, k)
        retriever = hybrid_retriever(self.nodes, self._index, filters, k, bm25=bm25)

        return hits_to_dicts(retriever.retrieve(query))


def open_disk_index(
    db_path: str, nodes: Any, settings: Any, collection: str = COLLECTION
) -> tuple[QdrantClient, IndexRetriever]:
    """Mở index on-disk -> (client cần đóng cuối run, retrieve_fn)."""
    client = QdrantClient(path=str(db_path))
    store = build_vector_store(client, collection)
    index = open_index(store, build_embedder(settings))
    return client, IndexRetriever(nodes, index)
