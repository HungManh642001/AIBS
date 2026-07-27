"""Trang scan: phát hiện bóc thiếu rồi thử lại ĐÚNG CÁCH, vẫn thiếu thì cảnh báo (không im lặng).

Với seed cố định, thử lại y nguyên tham số sẽ ra y hệt — nên mỗi kiểu nghi ngờ phải đổi thứ khác
nhau: bị cắt -> tăng max_tokens; lệch cấu trúc -> đổi seed.
"""
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


async def test_lech_cau_truc_thi_thu_lai_voi_seed_khac():
    """Cùng seed thì model trả y hệt -> thử lại phải ĐỔI SEED mới có cơ hội khác."""
    vision = VisionGhiNhan([{"text": _BANG_LECH}, {"text": _BANG_DU}])
    pages = await ingest_hsdt([("bg.pdf", "bang_gia", _pdf_scan())], vision, dpi=72)
    assert len(vision.calls) == 2
    assert vision.calls[1]["seed"] is not None and vision.calls[1]["seed"] != vision.calls[0]["seed"]
    assert pages[0].text == _BANG_DU and pages[0].canh_bao == ""


async def test_van_lech_sau_khi_thu_lai_thi_canh_bao():
    vision = VisionGhiNhan([{"text": _BANG_LECH}])   # lần nào cũng lệch
    pages = await ingest_hsdt([("bg.pdf", "bang_gia", _pdf_scan())], vision, dpi=72)
    assert len(vision.calls) == 2                    # thử lại đúng 1 lần rồi thôi
    assert "cột" in pages[0].canh_bao
    assert pages[0].text == _BANG_LECH               # vẫn giữ phần đọc được


async def test_trang_co_canh_bao_thi_khong_ghi_cache():
    """Không đóng băng một trang đọc lỗi — lần sau còn cơ hội đọc lại."""
    class Store:
        def __init__(self):
            self.puts = []

        def get(self, key):
            return None

        def put(self, key, pages):
            self.puts.append(key)

    store = Store()
    vision = VisionGhiNhan([{"text": _BANG_LECH}])
    await ingest_hsdt([("bg.pdf", "bang_gia", _pdf_scan())], vision, dpi=72, cache=store)
    assert store.puts == []


async def test_giu_ban_it_van_de_hon():
    """Thử lại tệ hơn -> giữ bản ĐẦU (chọn theo số vấn đề, không mù quáng lấy bản cuối)."""
    vision = VisionGhiNhan([{"text": _BANG_LECH},
                            {"text": "STT | Ten\n1 | ... \n2"}])   # lệch + tóm tắt
    pages = await ingest_hsdt([("bg.pdf", "bang_gia", _pdf_scan())], vision, dpi=72)
    assert pages[0].text == _BANG_LECH


async def test_text_thuong_khong_bi_thu_lai():
    vision = VisionGhiNhan([{"text": "ĐƠN DỰ THẦU\nKính gửi bên mời thầu"}])
    pages = await ingest_hsdt([("don.pdf", "don_du_thau", _pdf_scan())], vision, dpi=72)
    assert len(vision.calls) == 1 and pages[0].canh_bao == ""
