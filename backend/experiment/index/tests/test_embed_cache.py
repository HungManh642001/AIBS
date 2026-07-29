"""Cache embedding — dùng lại vector cũ mà KHÔNG được đổi một con số nào."""
from llama_index.core.schema import MetadataMode, TextNode

from experiment.index.embed_cache import (
    EmbedCache, cache_path, gan_embedding, khoa_node, noi_dung_nhung,
)
from experiment.index.embedder import DeterministicEmbedding


class DemEmbed(DeterministicEmbedding):
    """Đếm số text thực sự đi nhúng."""

    _dem: dict = {}

    def _get_text_embeddings(self, texts):
        DemEmbed._dem["n"] = DemEmbed._dem.get("n", 0) + len(texts)
        return super()._get_text_embeddings(texts)


def _nodes(n=3, tail=""):
    return [TextNode(text=f"nội dung điều khoản {i}{tail}",
                     metadata={"chunk_id": f"c{i}", "clause_doc": "bdl"}) for i in range(n)]


def _reset():
    DemEmbed._dem = {"n": 0}
    return DemEmbed()


# ---- khóa ----
def test_khoa_theo_noi_dung_khong_theo_id():
    """Hai node khác id nhưng CÙNG nội dung nhúng -> cùng khóa (dùng lại được)."""
    a = TextNode(text="x", metadata={})
    b = TextNode(text="x", metadata={})
    assert a.node_id != b.node_id
    assert khoa_node("m", a) == khoa_node("m", b)


def test_khoa_doi_khi_noi_dung_hoac_model_doi():
    a = TextNode(text="x", metadata={})
    assert khoa_node("m", a) != khoa_node("m", TextNode(text="y", metadata={}))
    assert khoa_node("m", a) != khoa_node("model-khac", a)


def test_khoa_tinh_tren_chuoi_SE_DUOC_NHUNG_khong_phai_node_text():
    """LlamaIndex nhúng cả metadata (MetadataMode.EMBED). Băm nhầm node.text sẽ trả về vector
    của một nội dung KHÁC khi metadata đổi — sai thầm lặng, không ai phát hiện."""
    a = TextNode(text="x", metadata={"clause_doc": "bdl"})
    b = TextNode(text="x", metadata={"clause_doc": "cdnt"})
    assert a.text == b.text
    assert noi_dung_nhung(a) == a.get_content(metadata_mode=MetadataMode.EMBED)
    assert khoa_node("m", a) != khoa_node("m", b)


# ---- hành vi cache ----
def test_lan_hai_khong_nhung_lai(tmp_path):
    cache = EmbedCache(tmp_path / "e.pkl")
    e = _reset()
    gan_embedding(_nodes(3), e, cache)
    assert DemEmbed._dem["n"] == 3

    DemEmbed._dem["n"] = 0
    stat = gan_embedding(_nodes(3), e, EmbedCache(tmp_path / "e.pkl"))
    assert DemEmbed._dem["n"] == 0
    assert stat == {"trung": 3, "nhung": 0}


def test_vector_tu_cache_trung_khit_vector_tinh_moi(tmp_path):
    """Cốt lõi của 'nhanh hơn nhưng kết quả không đổi' — sai một con số là hỏng cả retrieval."""
    e = _reset()
    goc = _nodes(4)
    gan_embedding(goc, e, EmbedCache(tmp_path / "e.pkl"))

    lai = _nodes(4)
    gan_embedding(lai, e, EmbedCache(tmp_path / "e.pkl"))

    for a, b in zip(goc, lai):
        assert a.embedding == b.embedding      # bằng TUYỆT ĐỐI, không phải xấp xỉ


def test_chunk_doi_noi_dung_thi_nhung_lai(tmp_path):
    e = _reset()
    gan_embedding(_nodes(3), e, EmbedCache(tmp_path / "e.pkl"))
    DemEmbed._dem["n"] = 0

    stat = gan_embedding(_nodes(3, tail=" ĐÃ SỬA"), e, EmbedCache(tmp_path / "e.pkl"))
    assert DemEmbed._dem["n"] == 3 and stat["trung"] == 0


def test_chi_nhung_phan_thieu(tmp_path):
    """Sửa 1 chunk trong 3 -> chỉ nhúng lại 1."""
    e = _reset()
    gan_embedding(_nodes(3), e, EmbedCache(tmp_path / "e.pkl"))

    hon_hop = _nodes(3)
    hon_hop[1] = TextNode(text="hoàn toàn mới", metadata={"chunk_id": "c1", "clause_doc": "bdl"})
    DemEmbed._dem["n"] = 0
    stat = gan_embedding(hon_hop, e, EmbedCache(tmp_path / "e.pkl"))

    assert DemEmbed._dem["n"] == 1
    assert stat == {"trung": 2, "nhung": 1}


def test_moi_node_deu_co_embedding_sau_khi_gan(tmp_path):
    e = _reset()
    ns = _nodes(5)
    gan_embedding(ns, e, EmbedCache(tmp_path / "e.pkl"))
    assert all(n.embedding is not None and len(n.embedding) > 0 for n in ns)


def test_file_hong_thi_bo_qua_chu_khong_gay(tmp_path):
    p = tmp_path / "e.pkl"
    p.write_bytes(b"day khong phai pickle")
    e = _reset()
    stat = gan_embedding(_nodes(2), e, EmbedCache(p))     # không được raise
    assert stat["nhung"] == 2


def test_cache_path_nam_trong_out_dir(tmp_path):
    assert cache_path(tmp_path).parent == tmp_path
