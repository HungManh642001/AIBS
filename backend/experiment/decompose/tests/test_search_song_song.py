"""Step search chạy các need SONG SONG — nghiệm thu 'nhanh hơn nhưng kết quả không đổi'.

Các test search sẵn có trong test_workflow.py đang đỏ vì lý do KHÁC (cơ chế neo mã điều khoản vào
query bị tắt), nên không dùng chúng để nghiệm thu phần song song hoá được. File này phủ riêng:
thứ tự thời gian đổi, nội dung KHÔNG đổi.
"""
import asyncio
import time

class _Out:
    """AiOutcome tối giản — llm_fn chỉ cần .status/.data/.error."""

    def __init__(self, data):
        self.status = "ok"
        self.data = data
        self.error = None


def _llm_cham(do_tre: float, dem: dict):
    """llm_fn giả: mỗi call ngủ `do_tre`; ghi lại số call ĐANG chạy đồng thời (đỉnh)."""
    async def llm(system, prompt, validate=None, max_tokens=None):
        dem["dang_chay"] += 1
        dem["dinh"] = max(dem["dinh"], dem["dang_chay"])
        try:
            await asyncio.sleep(do_tre)
            if "TAG:QUERY" in prompt:
                return _Out({"query": f"q-{dem['n_query']}", "nguon_goi_y": []})
            return _Out({"thong_tin_bo_sung": "giá trị X", "nguon": "A-BDL 1.1", "can_review": False})
        finally:
            dem["dang_chay"] -= 1
    return llm


def _retrieve_gia(ghi: list):
    """retrieve ĐỒNG BỘ (như thật) — ngủ bằng time.sleep để lộ ngay nếu quên to_thread."""
    def r(query, k=5, clause_doc=None, is_form=None, source_doc=None):
        time.sleep(0.02)
        ghi.append(query)
        return [{"text": "nội dung điều khoản", "metadata": {"chunk_id": f"c{len(ghi)}"}, "score": 1.0}]
    return r


def _crit(n_need: int):
    nds = [{"noi_dung_kiem_tra": f"nd{i}", "hsdt_kiem_tra": "don_du_thau", "yeu_cau": "theo HSMT",
            "can_lam_ro": f"cần rõ {i}", "can_tra_cuu": True, "thong_tin_bo_sung": "",
            "nguon": "", "can_review": False, "ap_dung": "", "dieu_kien_ap_dung": {}}
           for i in range(n_need)]
    return {"nhom": "hop_le", "ten": "Tiêu chí X", "yeu_cau_goc": "yêu cầu gốc",
            "hsdt_can_kiem_tra": ["don_du_thau"], "noi_dung_can_kiem_tra": nds}


def _wf(llm, retrieve, **kw):
    from experiment.decompose.workflow import DecomposeWorkflow
    return DecomposeWorkflow(llm_fn=llm, retrieve_fn=retrieve, **kw)


async def _chay_search(wf, crit):
    """Gọi thẳng phần thân song song của step search (không dựng cả Workflow)."""
    needs = [n for n in crit["noi_dung_can_kiem_tra"] if n["can_tra_cuu"]]
    await asyncio.gather(*(wf._xu_ly_need(crit, n, crit["ten"]) for n in needs))


async def test_cac_need_chay_song_song_chu_khong_noi_duoi():
    """6 need x 2 call x 50ms: tuần tự ~600ms, song song ~100ms. Chốt ở 350ms cho rộng tay."""
    dem = {"dang_chay": 0, "dinh": 0, "n_query": 0}
    crit = _crit(6)
    wf = _wf(_llm_cham(0.05, dem), _retrieve_gia([]))

    t0 = time.perf_counter()
    await _chay_search(wf, crit)
    mat = time.perf_counter() - t0

    assert mat < 0.35, f"vẫn tuần tự: {mat:.2f}s"
    assert dem["dinh"] > 1, "không có call nào chồng lên nhau -> chưa song song"


async def test_ket_qua_y_het_khi_chay_tuan_tu():
    """Cùng đầu vào -> song song và tuần tự phải cho ra CÙNG nội dung (chỉ khác thứ tự thời gian)."""
    dem = {"dang_chay": 0, "dinh": 0, "n_query": 0}
    song_song = _crit(5)
    await _chay_search(_wf(_llm_cham(0, dem), _retrieve_gia([])), song_song)

    tuan_tu = _crit(5)
    wf = _wf(_llm_cham(0, dem), _retrieve_gia([]))
    for n in tuan_tu["noi_dung_can_kiem_tra"]:          # đúng lối cũ: nối đuôi
        await wf._xu_ly_need(tuan_tu, n, tuan_tu["ten"])

    assert song_song["noi_dung_can_kiem_tra"] == tuan_tu["noi_dung_can_kiem_tra"]
    assert all(n["thong_tin_bo_sung"] == "giá trị X" for n in song_song["noi_dung_can_kiem_tra"])
    assert all(not n["can_review"] for n in song_song["noi_dung_can_kiem_tra"])


async def test_semaphore_chan_tran_so_need_dang_bay():
    """max_song_song=2 -> không bao giờ có quá 2 need (tức 2 call) chạy cùng lúc."""
    dem = {"dang_chay": 0, "dinh": 0, "n_query": 0}
    wf = _wf(_llm_cham(0.02, dem), _retrieve_gia([]), max_song_song=2)

    await _chay_search(wf, _crit(8))
    assert dem["dinh"] <= 2, f"vượt trần: đỉnh {dem['dinh']}"


async def test_retrieve_dong_bo_chay_trong_thread_khong_chan_event_loop():
    """retrieve là hàm SYNC (time.sleep 20ms). 6 need, LLM 0ms -> chỉ còn chi phí retrieve.

    Gọi thẳng trong async: event loop bị chặn, 6 x 20ms nối đuôi = ~120ms.
    Qua asyncio.to_thread: 6 cái chạy chồng nhau = ~20-30ms.
    """
    dem = {"dang_chay": 0, "dinh": 0, "n_query": 0}
    wf = _wf(_llm_cham(0, dem), _retrieve_gia([]))

    t0 = time.perf_counter()
    await _chay_search(wf, _crit(6))
    mat = time.perf_counter() - t0

    assert mat < 0.08, f"retrieve đang chặn event loop: {mat*1000:.0f}ms (nối đuôi sẽ ~120ms)"
