"""Cổng truy hồi cho workflow phân rã.

Thật: truy hồi hybrid trên index Qdrant on-disk (`experiment.index`). Test: tiêm in-memory
hoặc scripted. retrieve_fn(query, k, clause_doc=None, is_form=None, source_doc=None)
-> list[{text, metadata, score}]. clause_doc="bdl" -> chỉ Bảng dữ liệu E-BDL;
source_doc="tbmt" -> chỉ chunk của nguồn tài liệu đó (route theo nguồn).
"""
from __future__ import annotations

from typing import Any, Callable

from llama_index.core.vector_stores import FilterOperator, MetadataFilter, MetadataFilters
from qdrant_client import QdrantClient

from experiment.index.embedder import build_embedder
from experiment.index.schema import COLLECTION
from experiment.index.store import build_vector_store, open_index

# retrieve_fn(query, k, clause_doc=None) -> list[hit dict]
RetrieveFn = Callable[..., list[dict[str, Any]]]


def hits_to_dicts(hits: Any) -> list[dict[str, Any]]:
    return [
        {"text": h.node.text or "", "metadata": h.node.metadata or {}, "score": float(h.score or 0.0)}
        for h in hits
    ]


class IndexRetriever:
    """retrieve_fn dựa trên một VectorStoreIndex đã mở (giữ index sống suốt run)."""

    def __init__(self, index: Any):
        self._index = index

    def __call__(self, query: str, k: int = 5, clause_doc: str | None = None,
                 is_form: bool | None = None, source_doc: str | None = None) -> list[dict[str, Any]]:
        conds = []
        if clause_doc:
            conds.append(MetadataFilter(key="clause_doc", value=clause_doc, operator=FilterOperator.EQ))
        if is_form is not None:  # need 'đúng mẫu số N' -> tra VÀO chunk Biểu mẫu (payload int 0/1)
            conds.append(MetadataFilter(key="is_form", value=int(is_form), operator=FilterOperator.EQ))
        if source_doc:  # route theo nguồn tài liệu (hsmt/tbmt/...) — step-3 gợi ý từ danh mục nguồn
            conds.append(MetadataFilter(key="source_doc", value=source_doc, operator=FilterOperator.EQ))
        filters = MetadataFilters(filters=conds) if conds else None
        retriever = self._index.as_retriever(
            vector_store_query_mode="hybrid", similarity_top_k=k, sparse_top_k=k, filters=filters
        )
        return hits_to_dicts(retriever.retrieve(query))


def open_disk_index(
    db_path: str, settings: Any, collection: str = COLLECTION
) -> tuple[QdrantClient, IndexRetriever]:
    """Mở index on-disk -> (client cần đóng cuối run, retrieve_fn)."""
    client = QdrantClient(path=str(db_path))
    store = build_vector_store(client, collection)
    index = open_index(store, build_embedder(settings))
    return client, IndexRetriever(index)
