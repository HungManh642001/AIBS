"""Embedding cho vector index.

Thật: `OpenAILikeEmbedding` gọi endpoint OpenAI-compatible `/v1/embeddings` của LiteLLM proxy
(KHÔNG dùng lib litellm -> giữ pin litellm==1.41.0). Proxy lỗi -> raise, KHÔNG bịa vector
(no-silent-mock như services/ai_client.py).

Test: `DeterministicEmbedding` chạy offline, xác định — CHỈ dùng trong test.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any, List

from llama_index.core.embeddings import BaseEmbedding
from llama_index.embeddings.openai_like import OpenAILikeEmbedding

from experiment.index.schema import FAKE_DIM


def build_embedder(settings: Any) -> OpenAILikeEmbedding:
    """Dense embedder THẬT qua LiteLLM proxy (model `settings.ai_embed_model`)."""
    return OpenAILikeEmbedding(
        model_name=settings.ai_embed_model,
        api_base=settings.ai_base_url,
        api_key=settings.ai_api_key or "sk-no-key",
        is_chat_model=False,
    )


class DeterministicEmbedding(BaseEmbedding):
    """Embedding xác định, offline (hash(text) -> unit vector dim FAKE_DIM). CHỈ dùng test."""

    @classmethod
    def class_name(cls) -> str:
        return "DeterministicEmbedding"

    def _vec(self, text: str) -> List[float]:
        h = hashlib.sha256((text or "").encode("utf-8")).digest()
        raw = [(h[i % len(h)] - 128) / 128.0 for i in range(FAKE_DIM)]
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]

    def _get_query_embedding(self, query: str) -> List[float]:
        return self._vec(query)

    def _get_text_embedding(self, text: str) -> List[float]:
        return self._vec(text)

    async def _aget_query_embedding(self, query: str) -> List[float]:
        return self._vec(query)

    async def _aget_text_embedding(self, text: str) -> List[float]:
        return self._vec(text)
