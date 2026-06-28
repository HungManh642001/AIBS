"""Cổng truy hồi cho workflow phân rã.

Thật: truy hồi hybrid trên index Qdrant on-disk (`experiment.index`). Test: tiêm in-memory
hoặc scripted. retrieve_fn(query, k) -> list[{text, metadata, score}].
"""
from __future__ import annotations

from typing import Any, Callable

from qdrant_client import QdrantClient

from experiment.index.embedder import build_embedder
from experiment.index.schema import COLLECTION
from experiment.index.store import build_vector_store, hybrid_retriever, open_index

# retrieve_fn(query, k) -> list[hit dict]
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

    def __call__(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        return hits_to_dicts(hybrid_retriever(self._index, k).retrieve(query))


def open_disk_index(
    db_path: str, settings: Any, collection: str = COLLECTION
) -> tuple[QdrantClient, IndexRetriever]:
    """Mở index on-disk -> (client cần đóng cuối run, retrieve_fn)."""
    client = QdrantClient(path=str(db_path))
    store = build_vector_store(client, collection)
    index = open_index(store, build_embedder(settings))
    return client, IndexRetriever(index)
