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


def test_build_embedder_bao_loi_ngay_o_che_do_mock():
    """ABES_AI_MOCK=1: raise NGAY thay vì để llama_index retry vào proxy chết.

    KHÔNG rơi về DeterministicEmbedding: vector giả -> retrieval giả -> tiêu chí bịa.
    """
    import pytest as _pytest
    from types import SimpleNamespace
    from experiment.index.embedder import build_embedder

    s = SimpleNamespace(ai_mock=True, ai_embed_model="bge-m3",
                        ai_base_url="http://localhost:4000/v1", ai_api_key="")
    with _pytest.raises(RuntimeError, match="mock"):
        build_embedder(s)
