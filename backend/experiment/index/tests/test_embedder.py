import math

from experiment.index.embedder import DeterministicEmbedding, build_embedder
from experiment.index.schema import FAKE_DIM


def test_deterministic_dim_and_stable():
    e = DeterministicEmbedding()
    v1 = e.get_text_embedding("xin chào")
    v2 = e.get_text_embedding("xin chào")
    assert len(v1) == FAKE_DIM
    assert v1 == v2  # xác định
    assert e.get_text_embedding("văn bản khác") != v1


def test_deterministic_unit_norm():
    e = DeterministicEmbedding()
    v = e.get_query_embedding("tiêu chuẩn kỹ thuật")
    assert abs(math.sqrt(sum(x * x for x in v)) - 1.0) < 1e-6


def test_build_embedder_no_network():
    """Khởi tạo embedder thật KHÔNG gọi mạng (chỉ khi embed mới gọi proxy)."""

    class _S:
        ai_embed_model = "bge-m3"
        ai_base_url = "http://localhost:4000/v1"
        ai_api_key = ""

    emb = build_embedder(_S())
    assert getattr(emb, "model_name", None) == "bge-m3"
