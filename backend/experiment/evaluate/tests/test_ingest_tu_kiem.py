"""Trang scan: phát hiện bóc thiếu -> cảnh báo (không im lặng); chỉ đọc lại khi CHẠM TRẦN TOKEN.

Nghi ngờ do lệch cấu trúc (kiem_tra_bang) không còn kéo theo đọc lại: seed đã cố định nên gọi lại
chỉ đổi được seed, mà đo trên hồ sơ thật là 21 lần thử lại chỉ cứu được 1 — không đáng 2x call. Chỉ
chạm trần token (finish_reason == 'length') mới thử lại, vì tăng max_tokens là một call thực sự
khác, có cơ hội lấy lại phần bị cắt.
"""
import logging

import fitz

from experiment.evaluate.ingest import ingest_hsdt
from services.ai_client import AiOutcome


def _pdf_scan(text: str = "scan") -> bytes:
    """PDF không có text nhúng đáng kể -> buộc đi đường vision."""
    d = fitz.open()
    d.new_page().insert_text((72, 72), text)
    return d.tobytes()


class VisionGhiNhan:
    """Vision giả: trả lần lượt các kịch bản, ghi lại tham số từng call."""

    def __init__(self, ket_qua: list[dict]):
        self._kq = list(ket_qua)
        self.calls: list[dict] = []

    async def __call__(self, system, prompt, images=(), validate=None, max_tokens=None,
                       seed=None, **kw):
        self.calls.append({"max_tokens": max_tokens, "seed": seed})
        kq = self._kq[min(len(self.calls) - 1, len(self._kq) - 1)]
        data = {"text": kq["text"], "co_chu_ky": False, "co_dau": False}
        return AiOutcome("ok", validate(data) if validate else data, "fake",
                         finish_reason=kq.get("finish_reason", "stop"))


_BANG_DU = "STT | Ten | Tien\n1 | May chu | 100\n2 | UPS | 200"
_BANG_LECH = "STT | Ten | Tien\n1 | May chu | 100\n2 | UPS"


async def test_bi_cat_thi_thu_lai_voi_nhieu_token_hon():
    vision = VisionGhiNhan([{"text": _BANG_DU, "finish_reason": "length"},
                            {"text": _BANG_DU, "finish_reason": "stop"}])
    pages = await ingest_hsdt([("bg.pdf", "bang_gia", _pdf_scan())], vision, dpi=72)
    assert len(vision.calls) == 2
    assert vision.calls[1]["max_tokens"] > vision.calls[0]["max_tokens"]
    assert pages[0].canh_bao == ""                  # thử lại xong hết nghi ngờ


async def test_lech_cau_truc_chi_canh_bao_khong_doc_lai():
    """Nghi bóc thiếu -> CHỈ cảnh báo. Đo thực tế: thử lại cứu được ~5%, không đáng 2x call."""
    vision = VisionGhiNhan([{"text": _BANG_LECH}])
    pages = await ingest_hsdt([("bg.pdf", "bang_gia", _pdf_scan())], vision, dpi=72)
    assert len(vision.calls) == 1                    # KHÔNG đọc lại
    assert "cột" in pages[0].canh_bao
    assert pages[0].text == _BANG_LECH               # vẫn giữ phần đọc được


async def test_nghi_boc_thieu_chi_log_MOT_lan_cho_moi_trang(caplog):
    """Log này là NGUỒN SỐ LIỆU đo tỷ lệ bóc thiếu — bắn hai lần cho một trang là lệch phép đo."""
    vision = VisionGhiNhan([{"text": _BANG_LECH}])
    with caplog.at_level(logging.WARNING, logger="EVALUATE"):
        await ingest_hsdt([("bg.pdf", "bang_gia", _pdf_scan())], vision, dpi=72)
    dong = [r for r in caplog.records if "nghi bóc thiếu" in r.getMessage()]
    assert len(dong) == 1
    assert "bg.pdf" in dong[0].getMessage() and "tr1" in dong[0].getMessage()


async def test_trang_co_canh_bao_van_duoc_ghi_cache():
    """Cảnh báo là thông tin, không phải lỗi -> vẫn cache (kèm theo canh_bao), khỏi OCR lại cả file."""
    class Store:
        def __init__(self):
            self.puts: list[tuple[str, list[dict]]] = []

        def get(self, key):
            return None

        def put(self, key, pages):
            self.puts.append((key, pages))

    store = Store()
    vision = VisionGhiNhan([{"text": _BANG_LECH}])
    await ingest_hsdt([("bg.pdf", "bang_gia", _pdf_scan())], vision, dpi=72, cache=store)
    assert len(store.puts) == 1
    assert "cột" in store.puts[0][1][0]["canh_bao"]   # cảnh báo phải nằm TRONG payload cache


async def test_giu_ban_it_van_de_hon():
    """Thử lại (do chạm trần) tệ hơn -> giữ bản ĐẦU, không mù quáng lấy bản cuối."""
    vision = VisionGhiNhan([{"text": _BANG_LECH, "finish_reason": "length"},
                            {"text": "STT | Ten\n1 | ... \n2"}])   # lệch + tóm tắt
    pages = await ingest_hsdt([("bg.pdf", "bang_gia", _pdf_scan())], vision, dpi=72)
    assert len(vision.calls) == 2
    assert pages[0].text == _BANG_LECH


async def test_giu_ban_da_cham_tran_thi_van_canh_bao_bi_cat():
    """Cùng lỗ hổng với ca thử lại LỖI: giữ bản ĐÃ CHẠM TRẦN mà `canh_bao` rỗng thì text thiếu bị
    đóng băng vào cache. Bản đầu ở đây sạch theo `kiem_tra_bang` nên nếu không gắn cảnh báo cắt,
    trang ra `canh_bao=''` y như trang đọc tốt."""
    vision = VisionGhiNhan([{"text": _BANG_DU, "finish_reason": "length"},
                            {"text": "STT | Ten\n1 | ... \n2"}])   # thử lại còn tệ hơn
    pages = await ingest_hsdt([("bg.pdf", "bang_gia", _pdf_scan())], vision, dpi=72)
    assert len(vision.calls) == 2
    assert pages[0].text == _BANG_DU                  # vẫn giữ bản đầu (ít vấn đề hơn)
    assert "chạm trần token" in pages[0].canh_bao


async def test_text_thuong_khong_bi_thu_lai():
    vision = VisionGhiNhan([{"text": "ĐƠN DỰ THẦU\nKính gửi bên mời thầu"}])
    pages = await ingest_hsdt([("don.pdf", "don_du_thau", _pdf_scan())], vision, dpi=72)
    assert len(vision.calls) == 1 and pages[0].canh_bao == ""


async def test_trang_loi_vision_van_khong_ghi_cache():
    """Bất biến #1 giữ nguyên: LỖI vision không bao giờ được đóng băng vào cache."""
    from services.ai_client import AiOutcome

    class VisionLoi:
        def __init__(self):
            self.calls: list[dict] = []

        async def __call__(self, system, prompt, images=(), validate=None, max_tokens=None,
                           seed=None, **kw):
            self.calls.append({"max_tokens": max_tokens})
            return AiOutcome("error", None, "fake", error="proxy hỏng")

    class Store:
        def __init__(self):
            self.puts: list[str] = []

        def get(self, key):
            return None

        def put(self, key, pages):
            self.puts.append(key)

    store = Store()
    await ingest_hsdt([("bg.pdf", "bang_gia", _pdf_scan())], VisionLoi(), dpi=72, cache=store)
    assert store.puts == []


async def test_canh_bao_khoi_phuc_dung_khi_doc_tu_cache():
    """Cache mà nuốt mất canh_bao thì lần chấm thứ hai luật hết thấy cảnh báo -> sai âm thầm."""
    class Store:
        def __init__(self):
            self.data: dict[str, list[dict]] = {}

        def get(self, key):
            return self.data.get(key)

        def put(self, key, pages):
            self.data[key] = pages

    store = Store()
    pdf = _pdf_scan()
    v1 = VisionGhiNhan([{"text": _BANG_LECH}])
    p1 = await ingest_hsdt([("bg.pdf", "bang_gia", pdf)], v1, dpi=72, cache=store)
    v2 = VisionGhiNhan([{"text": _BANG_LECH}])
    p2 = await ingest_hsdt([("bg.pdf", "bang_gia", pdf)], v2, dpi=72, cache=store)
    assert v2.calls == []                            # lần 2 đọc cache, 0 call
    assert p2[0].canh_bao == p1[0].canh_bao and "cột" in p2[0].canh_bao


async def test_cham_tran_ma_thu_lai_loi_thi_van_canh_bao_text_bi_cat():
    """Chạm trần token + lần thử lại LỖI -> trang BỊ CẮT vẫn được cache (cảnh báo không chặn cache),
    nên cảnh báo 'chạm trần token' PHẢI được ghi kèm; thiếu nó là đóng băng text thiếu vĩnh viễn."""
    class VisionCatRoiLoi:
        """Call 1: ok mà chạm trần (text SẠCH nên kiem_tra_bang không bắt gì). Call 2: lỗi."""

        def __init__(self):
            self.calls: list[dict] = []

        async def __call__(self, system, prompt, images=(), validate=None, max_tokens=None,
                           seed=None, **kw):
            self.calls.append({"max_tokens": max_tokens})
            if len(self.calls) == 1:
                data = {"text": _BANG_DU, "co_chu_ky": False, "co_dau": False}
                return AiOutcome("ok", validate(data) if validate else data, "fake",
                                 finish_reason="length")
            return AiOutcome("error", None, "fake", error="proxy hỏng")

    class Store:
        def __init__(self):
            self.puts: list[list[dict]] = []

        def get(self, key):
            return None

        def put(self, key, pages):
            self.puts.append(pages)

    store = Store()
    vision = VisionCatRoiLoi()
    pages = await ingest_hsdt([("bg.pdf", "bang_gia", _pdf_scan())], vision, dpi=72, cache=store)
    assert len(vision.calls) == 2
    assert pages[0].text == _BANG_DU                    # giữ phần đọc được của call 1
    assert "chạm trần token" in pages[0].canh_bao       # KHÔNG im lặng
    assert "chạm trần token" in store.puts[0][0]["canh_bao"]   # cảnh báo theo vào cache


async def test_entry_cache_cu_khong_co_khoa_canh_bao_van_doc_duoc():
    """Tương thích ngược: entry ghi trước thay đổi này không có khoá canh_bao -> ra '', không nổ."""
    from experiment.evaluate.ingest import ingest_cache_key

    pdf = _pdf_scan()
    key = ingest_cache_key(pdf, 72)

    class Store:
        def __init__(self):
            self.data = {key: [{"trang": 1, "text": "text cũ", "co_chu_ky": False,
                                "co_dau": False, "nguon_trich": "vision"}]}

        def get(self, k):
            return self.data.get(k)

        def put(self, k, pages):
            self.data[k] = pages

    vision = VisionGhiNhan([{"text": _BANG_DU}])
    pages = await ingest_hsdt([("bg.pdf", "bang_gia", pdf)], vision, dpi=72, cache=Store())
    assert vision.calls == [] and pages[0].text == "text cũ" and pages[0].canh_bao == ""
