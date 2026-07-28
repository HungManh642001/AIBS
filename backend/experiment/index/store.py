"""Qdrant vector store (hybrid dense + sparse BM25) qua LlamaIndex."""
from __future__ import annotations

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import TextNode
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.vector_stores import MetadataFilters

from qdrant_client import QdrantClient

from experiment.index.schema import COLLECTION


def build_vector_store(client: QdrantClient, collection: str = COLLECTION) -> QdrantVectorStore:
    """QdrantVectorStore hybrid: dense (cosine) + sparse BM25, hợp nhất bằng RRF."""
    return QdrantVectorStore(
        collection_name=collection,
        client=client,
    )


def build_index(
    nodes: list[TextNode], store: QdrantVectorStore, embed: BaseEmbedding
) -> VectorStoreIndex:
    """Dựng collection từ nodes (dense = embed, sparse = BM25 tự sinh)."""
    storage = StorageContext.from_defaults(vector_store=store)
    return VectorStoreIndex(nodes, storage_context=storage, embed_model=embed)


def open_index(store: QdrantVectorStore, embed: BaseEmbedding) -> VectorStoreIndex:
    """Mở lại index từ collection đã có (không build lại)."""
    return VectorStoreIndex.from_vector_store(store, embed_model=embed)


def build_bm25(nodes: list[TextNode], filters: MetadataFilters = None, k: int = 5) -> BM25Retriever:
    """Dựng BM25 trên toàn bộ nodes — ĐẮT (tokenize + stem cả corpus).

    Đo trên 377 chunk: dựng 85ms, truy vấn 0.9ms. Retriever KHÔNG giữ trạng thái giữa các truy
    vấn nên dùng lại được; bên gọi nên cache theo (k, filters) thay vì dựng mỗi lần retrieve.
    """
    return BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=k, filters=filters)


def hybrid_retriever(nodes: list[TextNode], index: VectorStoreIndex, filters: MetadataFilters = None,
                     k: int = 5, bm25: BM25Retriever | None = None) -> BaseRetriever:
    """Retriever hybrid top-k (dense + sparse).

    `bm25`: truyền retriever đã dựng sẵn để khỏi dựng lại (xem build_bm25). Không truyền thì dựng
    mới — giữ nguyên hành vi cũ cho bên gọi khác.
    """
    vector_retriever = index.as_retriever(similarity_top_k=k, filters=filters)
    bm25_retriever = bm25 if bm25 is not None else build_bm25(nodes, filters, k)
    return QueryFusionRetriever(
        retrievers=[vector_retriever, bm25_retriever],
        similarity_top_k=2*k,
        num_queries=1,       # disable query expansion, only fuse results
        mode="reciprocal_rerank",
        use_async=False,
    )
