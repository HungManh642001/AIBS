"""Qdrant vector store (hybrid dense + sparse BM25) qua LlamaIndex."""
from __future__ import annotations

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import TextNode
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from experiment.index.schema import COLLECTION

_SPARSE_MODEL = "Qdrant/bm25"  # sparse BM25 local (FastEmbed), xác định, không cần proxy


def build_vector_store(client: QdrantClient, collection: str = COLLECTION) -> QdrantVectorStore:
    """QdrantVectorStore hybrid: dense (cosine) + sparse BM25, hợp nhất bằng RRF."""
    return QdrantVectorStore(
        collection_name=collection,
        client=client,
        enable_hybrid=True,
        fastembed_sparse_model=_SPARSE_MODEL,
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


def hybrid_retriever(index: VectorStoreIndex, k: int = 5) -> BaseRetriever:
    """Retriever hybrid top-k (dense + sparse)."""
    return index.as_retriever(
        vector_store_query_mode="hybrid",
        similarity_top_k=k,
        sparse_top_k=k,
    )
