"""Cache call LLM của decompose — trúng thì 0 call, và không được dùng nhầm kết quả prompt khác."""
import json

from experiment.decompose.cache import FileCallCache, boc_cache, cache_path, khoa_goi


class _Out:
    def __init__(self, status="ok", data=None, error=None):
        self.status, self.data, self.error, self.model = status, data, error, "fake"


def _llm(dem: dict, data=None, status="ok"):
    async def goi(system, prompt, validate=None, max_tokens=None):
        dem["n"] += 1
        return _Out(status=status, data=data if data is not None else {"query": prompt[:10]})
    return goi


# ---- khóa ----
def test_khoa_doi_khi_prompt_doi():
    a = khoa_goi("m", "sys", "prompt A", 100)
    assert a != khoa_goi("m", "sys", "prompt B", 100)
    assert a != khoa_goi("m", "sys KHÁC", "prompt A", 100)
    assert a != khoa_goi("model KHÁC", "sys", "prompt A", 100)
    assert a != khoa_goi("m", "sys", "prompt A", 200)      # max_tokens cũng vào khóa
    assert a == khoa_goi("m", "sys", "prompt A", 100)      # cùng đầu vào -> cùng khóa


def test_khoa_khong_nhap_nhang_khi_ghep_chuoi():
    """'ab'+'c' và 'a'+'bc' phải ra khóa KHÁC nhau (có ký tự ngăn cách)."""
    assert khoa_goi("m", "ab", "c", None) != khoa_goi("m", "a", "bc", None)


# ---- hành vi cache ----
async def test_trung_cache_thi_khong_goi_model(tmp_path):
    dem = {"n": 0}
    cache = FileCallCache(tmp_path / "c.json")
    goi = boc_cache(_llm(dem, {"query": "X"}), cache, model="m")

    a = await goi("sys", "prompt", max_tokens=10)
    b = await goi("sys", "prompt", max_tokens=10)

    assert dem["n"] == 1, "lần 2 vẫn gọi model -> cache không ăn"
    assert a.data == b.data == {"query": "X"}
    assert "cache" in b.model                      # nói rõ kết quả từ đâu, cho audit
    assert goi.dem == {"trung": 1, "truot": 1}


async def test_prompt_khac_thi_khong_dung_lai(tmp_path):
    dem = {"n": 0}
    goi = boc_cache(_llm(dem), FileCallCache(tmp_path / "c.json"), model="m")
    await goi("sys", "prompt A")
    await goi("sys", "prompt B")
    assert dem["n"] == 2


async def test_khong_cache_luot_loi(tmp_path):
    """Proxy lỗi mà cache lại thì lần sau vẫn hỏng dù proxy đã sống (no-silent-mock)."""
    dem = {"n": 0}
    cache = FileCallCache(tmp_path / "c.json")
    goi = boc_cache(_llm(dem, data=None, status="error"), cache, model="m")

    await goi("sys", "prompt")
    await goi("sys", "prompt")
    assert dem["n"] == 2 and len(cache) == 0


async def test_cache_song_qua_lan_chay_moi(tmp_path):
    """Ghi ra file -> tiến trình sau nạp lại được (đây chính là mục đích)."""
    dem = {"n": 0}
    p = tmp_path / "c.json"
    await boc_cache(_llm(dem, {"query": "X"}), FileCallCache(p), model="m")("sys", "prompt")

    dem2 = {"n": 0}
    out = await boc_cache(_llm(dem2, {"query": "Y"}), FileCallCache(p), model="m")("sys", "prompt")

    assert dem2["n"] == 0 and out.data == {"query": "X"}


async def test_file_hong_thi_bo_qua_chu_khong_gay_run(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{ đây không phải JSON", encoding="utf-8")
    dem = {"n": 0}
    cache = FileCallCache(p)                       # không được raise
    out = await boc_cache(_llm(dem, {"query": "X"}), cache, model="m")("sys", "prompt")
    assert out.data == {"query": "X"} and dem["n"] == 1


def test_cache_path_nam_trong_workdir(tmp_path):
    assert cache_path(tmp_path).parent == tmp_path
    assert cache_path(tmp_path).name.endswith(".json")


async def test_ghi_ra_file_doc_duoc_bang_json(tmp_path):
    p = tmp_path / "c.json"
    await boc_cache(_llm({"n": 0}, {"query": "Đơn dự thầu"}), FileCallCache(p), model="m")(
        "sys", "prompt")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert list(d.values()) == [{"query": "Đơn dự thầu"}]   # giữ tiếng Việt, soi tay được
