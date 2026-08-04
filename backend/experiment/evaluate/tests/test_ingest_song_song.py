"""Ingest đọc các trang SONG SONG — phần tốn nhất của một lượt chấm (731s/1507s đo trên log thật)."""
import fitz

from experiment.evaluate.ingest import ingest_hsdt
from experiment.evaluate.tests.dong_thoi import VisionDemDongThoi


def _pdf_scan(n: int) -> bytes:
    """PDF n trang KHÔNG có text nhúng -> mọi trang buộc đi đường vision."""
    d = fitz.open()
    for _ in range(n):
        d.new_page()
    return d.tobytes()


async def test_cac_trang_doc_song_song():
    vision = VisionDemDongThoi()
    pages = await ingest_hsdt([("scan.pdf", "bao_dam_du_thau", _pdf_scan(6))], vision, dpi=72)
    assert len(pages) == 6
    assert vision.so_call == 6
    assert vision.dinh > 1, "các trang vẫn đọc tuần tự"


async def test_thu_tu_trang_giu_nguyen():
    """gather giữ thứ tự — số trang phải đúng 1..n, không đảo."""
    vision = VisionDemDongThoi()
    pages = await ingest_hsdt([("scan.pdf", "bao_dam_du_thau", _pdf_scan(5))], vision, dpi=72)
    assert [p.trang for p in pages] == [1, 2, 3, 4, 5]


async def test_ket_qua_giong_het_duong_tuan_tu():
    """Bất biến quan trọng nhất: song song KHÔNG được đổi nội dung đọc ra."""
    pdf = _pdf_scan(4)
    a = await ingest_hsdt([("s.pdf", "bang_gia", pdf)], VisionDemDongThoi({"text": "A"}), dpi=72)
    b = await ingest_hsdt([("s.pdf", "bang_gia", pdf)], VisionDemDongThoi({"text": "A"}), dpi=72)
    assert [(p.trang, p.text, p.nguon_trich, p.canh_bao) for p in a] == \
           [(p.trang, p.text, p.nguon_trich, p.canh_bao) for p in b]


async def test_trang_co_text_nhung_van_khong_goi_vision():
    """Hồi quy: hai pha không được làm trang text nhúng lọt vào đường vision."""
    d = fitz.open()
    pg = d.new_page()
    # insert_textbox (không phải insert_text) để có wrap thật: cần đủ ký tự vượt NGUONG_TEXT
    # (200, xem pdf_text.py) mới chắc chắn được coi là trang có text nhúng, không phải scan.
    cau = "Đây là trang có text nhúng đủ dài để không bị coi là scan. "
    pg.insert_textbox(fitz.Rect(50, 50, 500, 700), cau * 5)
    d.new_page()                                   # trang trắng -> vision
    vision = VisionDemDongThoi()
    pages = await ingest_hsdt([("hh.pdf", "don_du_thau", d.tobytes())], vision, dpi=72)
    assert vision.so_call == 1                     # CHỈ trang trắng đi vision
    assert pages[0].nguon_trich == "pdf_text" and pages[1].nguon_trich == "vision"


async def test_render_xong_het_truoc_khi_thuc_su_song_song(monkeypatch):
    """PyMuPDF KHÔNG an toàn đa luồng: mọi việc đụng fitz (kể cả render PNG) phải xong TRƯỚC khi
    pha 2 thả các call vision chạy chồng nhau. Test khoá đúng ranh giới đó bằng thứ tự sự kiện."""
    import experiment.evaluate.ingest as ing

    nhat_ky: list[str] = []
    goc = ing.page_to_png
    monkeypatch.setattr(ing, "page_to_png",
                        lambda page, dpi=200: (nhat_ky.append("render"), goc(page, dpi=dpi))[1])

    class _GhiNhan(VisionDemDongThoi):
        async def __call__(self, system, prompt, images=(), validate=None, **kw):
            nhat_ky.append("vision")
            return await super().__call__(system, prompt, images, validate, **kw)

    await ingest_hsdt([("scan.pdf", "bang_gia", _pdf_scan(4))], _GhiNhan(), dpi=72)
    assert nhat_ky == ["render"] * 4 + ["vision"] * 4, f"thứ tự sai: {nhat_ky}"
