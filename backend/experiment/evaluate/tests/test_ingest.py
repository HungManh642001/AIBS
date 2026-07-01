import fitz

from experiment.evaluate.ingest import ingest_hsdt
from experiment.evaluate.vision import ScriptedVision


def _pdf(text: str) -> bytes:
    d = fitz.open(); p = d.new_page(); p.insert_text((72, 72), text)
    return d.tobytes()


async def test_ingest_transcribes_and_classifies_each_page():
    vision = ScriptedVision({"[IN]": {"loai_ho_so": "don_du_thau", "text": "Đơn dự thầu ...",
                                      "co_chu_ky": True, "co_dau": True}})
    pages = await ingest_hsdt([("don.pdf", _pdf("Đơn dự thầu"))], vision, dpi=100)
    assert len(pages) == 1
    p = pages[0]
    assert p.file == "don.pdf" and p.trang == 1
    assert p.loai_ho_so == "don_du_thau" and p.co_chu_ky is True
    assert p.image and p.image[:4] == b"\x89PNG"     # ảnh được giữ để evaluate soi thị giác


async def test_ingest_vision_error_keeps_page_no_fabrication():
    vision = ScriptedVision({"[IN]": RuntimeError("proxy down")})
    pages = await ingest_hsdt([("x.pdf", _pdf("abc"))], vision, dpi=100)
    assert len(pages) == 1
    assert pages[0].loai_ho_so == "khac" and pages[0].text == ""   # lỗi -> KHÔNG bịa
    assert pages[0].image  # vẫn giữ ảnh để người soi
