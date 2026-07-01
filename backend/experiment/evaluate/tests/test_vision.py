import fitz

from experiment.evaluate.vision import pdf_to_images, ScriptedVision


def _pdf(text: str) -> bytes:
    d = fitz.open(); p = d.new_page(); p.insert_text((72, 72), text)
    return d.tobytes()


def test_pdf_to_images_one_png_per_page():
    data = _pdf("ĐƠN DỰ THẦU")
    imgs = pdf_to_images(data, dpi=120)
    assert len(imgs) == 1
    assert imgs[0][:8] == b"\x89PNG\r\n\x1a\n"   # PNG signature


async def test_scripted_vision_matches_tag_and_counts_images():
    sv = ScriptedVision({"[IN]": {"loai_ho_so": "don_du_thau", "text": "x"}})
    out = await sv("sys", "prompt [IN] here", images=[b"img1", b"img2"])
    assert out.status == "ok" and out.data["loai_ho_so"] == "don_du_thau"
    assert sv.calls[-1][1] == 2     # đếm số ảnh đã gửi


async def test_scripted_vision_error_on_exception_and_no_match():
    sv = ScriptedVision({"[BOOM]": RuntimeError("proxy down")})
    e1 = await sv("s", "x [BOOM] y")
    assert e1.status == "error" and "proxy down" in e1.error
    e2 = await sv("s", "no tag")
    assert e2.status == "error"
