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


def hybrid_retriever(nodes: list[TextNode], index: VectorStoreIndex, filters: MetadataFilters = None, k: int = 5) -> BaseRetriever:
    """Retriever hybrid top-k (dense + sparse)."""
    vector_retriever = index.as_retriever(similarity_top_k=k, filters=filters)
    # return vector_retriever
    bm25_retriever = BM25Retriever.from_defaults(
        nodes=nodes,
        similarity_top_k=k,
        filters=filters
    )
    return QueryFusionRetriever(
        retrievers=[vector_retriever, bm25_retriever],
        similarity_top_k=2*k,
        num_queries=1,       # disable query expansion, only fuse results
        mode="reciprocal_rerank",
        use_async=False,
    )
