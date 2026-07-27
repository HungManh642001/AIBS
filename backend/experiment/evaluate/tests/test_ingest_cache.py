"""Cache vision-ingest: chỉ OCR lại khi tài liệu mới/đổi nội dung (hoặc đổi dpi/prompt ingest)."""
import fitz

from experiment.evaluate.ingest import ingest_cache_key, ingest_hsdt
from experiment.evaluate.vision import ScriptedVision


def _pdf(text: str) -> bytes:
    d = fitz.open(); p = d.new_page(); p.insert_text((72, 72), text)
    return d.tobytes()


class DictCache:
    """PageCache trong RAM — đủ để khoá hành vi lõi (adapter DB test riêng)."""

    def __init__(self, seed: dict | None = None):
        self.data = dict(seed or {})
        self.puts: list[str] = []

    def get(self, key):
        return self.data.get(key)

    def put(self, key, pages):
        self.data[key] = pages
        self.puts.append(key)


_OK = {"[IN]": {"text": "Đơn dự thầu ...", "co_chu_ky": True, "co_dau": False}}


def _pdf_bang(chu: str = "STT") -> bytes:
    """PDF có text nhúng + bảng, KHÔNG ảnh -> đủ điều kiện đi đường tất định."""
    d = fitz.open()
    pg = d.new_page()
    xs = [50, 200, 350]
    ys = [60 + 30 * i for i in range(5)]          # 4 hàng -> vượt ngưỡng text nhúng
    for x in xs:
        pg.draw_line(fitz.Point(x, ys[0]), fitz.Point(x, ys[-1]))
    for y in ys:
        pg.draw_line(fitz.Point(xs[0], y), fitz.Point(xs[-1], y))
    pg.insert_text((55, ys[0] + 20), chu, fontsize=5)
    pg.insert_text((205, ys[0] + 20), "Ten hang " + "x" * 60, fontsize=5)
    for i in range(1, 4):
        pg.insert_text((55, ys[i] + 20), str(i), fontsize=5)
        pg.insert_text((205, ys[i] + 20), f"May chu {i} " + "y" * 60, fontsize=5)
    return d.tobytes()


async def test_trang_co_text_nhung_khong_goi_vision():
    """Trang PDF có text nhúng -> đọc tất định, KHÔNG qua LLM (diệt gốc bất ổn khi đọc bảng)."""
    vision = ScriptedVision(dict(_OK))
    pages = await ingest_hsdt([("bg.pdf", "bang_gia", _pdf_bang())], vision, dpi=100)
    assert vision.calls == []
    assert len(pages) == 1 and "May chu" in pages[0].text and " | " in pages[0].text
    assert pages[0].nguon_trich == "pdf_text"


async def test_trang_scan_van_di_duong_vision():
    vision = ScriptedVision(dict(_OK))
    pages = await ingest_hsdt([("scan.pdf", "don_du_thau", _pdf("Đơn"))], vision, dpi=100)
    assert len(vision.calls) == 1
    assert pages[0].text == "Đơn dự thầu ..." and pages[0].nguon_trich == "vision"


async def test_file_hon_hop_chi_goi_vision_dung_trang_scan():
    """Bảng giá thật hay có 5 trang bảng sạch + 1 trang ký -> chỉ trang ký cần vision."""
    d = fitz.open(stream=_pdf_bang(), filetype="pdf")
    d.insert_pdf(fitz.open(stream=_pdf("trang scan"), filetype="pdf"))
    data = d.tobytes()
    d.close()
    vision = ScriptedVision(dict(_OK))
    pages = await ingest_hsdt([("bg.pdf", "bang_gia", data)], vision, dpi=100)
    assert len(pages) == 2
    assert [p.nguon_trich for p in pages] == ["pdf_text", "vision"]
    assert len(vision.calls) == 1                   # chỉ 1 call cho trang scan


async def test_key_doi_khi_doi_cach_trich():
    """Đổi logic trích -> khóa cache đổi, không ăn lại text bóc theo cách cũ."""
    import experiment.evaluate.ingest as mod
    data = _pdf("A")
    truoc = ingest_cache_key(data, 200)
    mod_ver = mod.TRICH_VERSION
    try:
        mod.TRICH_VERSION = mod_ver + "-x"
        assert ingest_cache_key(data, 200) != truoc
    finally:
        mod.TRICH_VERSION = mod_ver


def test_key_doi_khi_noi_dung_file_doi():
    assert ingest_cache_key(_pdf("A"), 200) != ingest_cache_key(_pdf("B"), 200)


def test_key_giu_nguyen_voi_cung_noi_dung():
    data = _pdf("A")
    assert ingest_cache_key(data, 200) == ingest_cache_key(data, 200)


def test_key_doi_khi_dpi_doi():
    data = _pdf("A")
    assert ingest_cache_key(data, 200) != ingest_cache_key(data, 100)


def test_key_doi_khi_prompt_ingest_doi(monkeypatch):
    """Sửa prompt ingest -> cache cũ tự vô hiệu (không phụ thuộc việc nhớ tăng số phiên bản)."""
    data = _pdf("A")
    truoc = ingest_cache_key(data, 200)
    monkeypatch.setattr("experiment.evaluate.ingest.SYS_INGEST", "PROMPT MỚI KHÁC HẲN")
    assert ingest_cache_key(data, 200) != truoc


async def test_cache_miss_thi_ocr_va_ghi_cache():
    vision = ScriptedVision(dict(_OK))
    cache = DictCache()
    data = _pdf("Đơn")
    pages = await ingest_hsdt([("don.pdf", "don_du_thau", data)], vision, dpi=100, cache=cache)
    assert pages[0].text == "Đơn dự thầu ..."
    assert len(vision.calls) == 1
    assert cache.puts == [ingest_cache_key(data, 100)]


async def test_cache_hit_thi_khong_goi_vision():
    data = _pdf("Đơn")
    key = ingest_cache_key(data, 100)
    cache = DictCache({key: [{"trang": 1, "text": "text đã lưu", "co_chu_ky": True,
                              "co_dau": True}]})
    vision = ScriptedVision(dict(_OK))
    pages = await ingest_hsdt([("don.pdf", "don_du_thau", data)], vision, dpi=100, cache=cache)
    assert vision.calls == []                       # KHÔNG gọi LLM -> đây là chỗ tiết kiệm
    assert len(pages) == 1
    p = pages[0]
    assert p.text == "text đã lưu" and p.co_chu_ky is True and p.co_dau is True
    assert p.file == "don.pdf" and p.trang == 1 and p.loai_ho_so == "don_du_thau"
    assert cache.puts == []                         # hit thì không ghi lại


async def test_cache_hit_van_dung_lai_anh_tu_pdf():
    """Ảnh KHÔNG nằm trong cache nhưng render lại từ PDF (rẻ, không tốn LLM) -> vẫn có ảnh."""
    data = _pdf("Đơn")
    key = ingest_cache_key(data, 100)
    cache = DictCache({key: [{"trang": 1, "text": "x", "co_chu_ky": False, "co_dau": False}]})
    pages = await ingest_hsdt([("don.pdf", "don_du_thau", data)], ScriptedVision({}), dpi=100,
                              cache=cache)
    assert pages[0].image and pages[0].image[:4] == b"\x89PNG"


async def test_trang_loi_vision_thi_KHONG_ghi_cache():
    """Lỗi proxy tạm thời mà cache lại thì text rỗng bị đóng băng vĩnh viễn -> cấm ghi."""
    vision = ScriptedVision({"[IN]": RuntimeError("proxy down")})
    cache = DictCache()
    pages = await ingest_hsdt([("don.pdf", "don_du_thau", _pdf("Đơn"))], vision, dpi=100,
                              cache=cache)
    assert pages[0].text == "" and cache.puts == []


async def test_khong_truyen_cache_thi_hanh_vi_nhu_cu():
    vision = ScriptedVision(dict(_OK))
    pages = await ingest_hsdt([("don.pdf", "don_du_thau", _pdf("Đơn"))], vision, dpi=100)
    assert pages[0].text == "Đơn dự thầu ..." and len(vision.calls) == 1


async def test_moi_file_mot_khoa_rieng():
    """2 file khác nội dung: file đã cache không gọi lại, file mới vẫn OCR."""
    cu, moi = _pdf("Cũ"), _pdf("Mới")
    cache = DictCache({ingest_cache_key(cu, 100): [
        {"trang": 1, "text": "cũ", "co_chu_ky": False, "co_dau": False}]})
    vision = ScriptedVision(dict(_OK))
    pages = await ingest_hsdt([("cu.pdf", "don_du_thau", cu),
                               ("moi.pdf", "bang_gia", moi)], vision, dpi=100, cache=cache)
    assert [p.text for p in pages] == ["cũ", "Đơn dự thầu ..."]
    assert len(vision.calls) == 1                   # chỉ OCR file mới
    assert cache.puts == [ingest_cache_key(moi, 100)]
