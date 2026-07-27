"""Cache kết quả chấm — chấm lại cùng hồ sơ + cùng tiêu chí phải ra Y HỆT, không hỏi lại model.

Mọi call LLM lúc chấm đều đi qua MỘT cửa `vision_fn`, nên bọc một lớp là phủ hết (eval, dò hình
thức, mọi luật) — không phải sửa dòng nào trong các luật.
"""
from experiment.evaluate.cached_vision import CachedVision, khoa_call
from experiment.evaluate.vision import ScriptedVision


class DictStore:
    def __init__(self, seed=None):
        self.data = dict(seed or {})
        self.puts: list[str] = []

    def get(self, key):
        return self.data.get(key)

    def put(self, key, data):
        self.data[key] = data
        self.puts.append(key)


_KB = {"[EV:X]": {"ket_qua": "đạt", "bang_chung": "ok", "trang": [1]}}


def test_khoa_doi_khi_prompt_doi():
    """Đổi tiêu chí -> prompt đổi -> khóa đổi -> chấm mới (không ăn kết quả cũ)."""
    assert khoa_call("sys", "prompt A", 4096) != khoa_call("sys", "prompt B", 4096)


def test_khoa_doi_khi_system_doi():
    assert khoa_call("sys A", "p", 4096) != khoa_call("sys B", "p", 4096)


def test_khoa_giu_nguyen_voi_cung_dau_vao():
    assert khoa_call("sys", "p", 4096) == khoa_call("sys", "p", 4096)


async def test_lan_dau_goi_that_va_ghi_cache():
    inner = ScriptedVision(dict(_KB))
    store = DictStore()
    cv = CachedVision(inner, store)
    out = await cv("sys", "[EV:X] nội dung")
    assert out.status == "ok" and out.data["ket_qua"] == "đạt"
    assert len(inner.calls) == 1 and len(store.puts) == 1


async def test_lan_sau_doc_cache_khong_goi_model():
    inner = ScriptedVision(dict(_KB))
    store = DictStore()
    cv = CachedVision(inner, store)
    a = await cv("sys", "[EV:X] nội dung")
    b = await cv("sys", "[EV:X] nội dung")
    assert len(inner.calls) == 1                    # chỉ hỏi model 1 lần
    assert a.data == b.data                         # và kết quả Y HỆT


async def test_ket_qua_giong_het_du_model_doi_y():
    """Model đổi ý giữa 2 lần chạy -> cache giữ kết quả ĐẦU, chấm lại vẫn ra như cũ."""
    store = DictStore()
    lan_1 = ScriptedVision({"[EV:X]": {"ket_qua": "đạt", "bang_chung": "ok"}})
    lan_2 = ScriptedVision({"[EV:X]": {"ket_qua": "không đạt", "bang_chung": "khác hẳn"}})
    a = await CachedVision(lan_1, store)("sys", "[EV:X] nội dung")
    b = await CachedVision(lan_2, store)("sys", "[EV:X] nội dung")
    assert a.data == b.data and lan_2.calls == []


async def test_khong_cache_khi_loi():
    """Proxy lỗi mà cache lại thì lỗi tạm thời hóa vĩnh viễn -> cấm ghi."""
    inner = ScriptedVision({})                      # không khớp kịch bản -> error
    store = DictStore()
    out = await CachedVision(inner, store)("sys", "[EV:X]")
    assert out.status == "error" and store.puts == []


async def test_call_kem_anh_khong_qua_cache():
    """Call có ảnh là của ingest — đã có cache riêng ở tầng trên, cache lại là thừa."""
    inner = ScriptedVision({"[IN]": {"text": "abc"}})
    store = DictStore()
    cv = CachedVision(inner, store)
    await cv("sys", "[IN]", images=[b"png"])
    await cv("sys", "[IN]", images=[b"png"])
    assert len(inner.calls) == 2 and store.puts == []


async def test_validate_van_chay_tren_du_lieu_cache():
    """Dữ liệu lấy từ cache vẫn phải qua validate — schema đổi thì không nuốt dữ liệu cũ sai kiểu."""
    store = DictStore({khoa_call("sys", "[EV:X]", 4096): {"ket_qua": "đạt", "thua": 1}})
    goi = []

    def validate(d):
        goi.append(d)
        return {"ket_qua": d["ket_qua"]}

    out = await CachedVision(ScriptedVision({}), store)("sys", "[EV:X]", validate=validate)
    assert out.status == "ok" and out.data == {"ket_qua": "đạt"} and goi
