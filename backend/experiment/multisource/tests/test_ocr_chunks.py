import fitz

from experiment.evaluate.vision import ScriptedVision
from experiment.multisource.ocr_chunks import SYS_OCR, ocr_scan_to_chunks, _split_text


def _pdf(text: str) -> bytes:
    d = fitz.open()
    d.new_page().insert_htmlbox(fitz.Rect(72, 72, 500, 300), f"<p>{text}</p>")
    return d.tobytes()


def test_split_text_windows():
    parts = _split_text("a" * 700 + "\n" + "b" * 100, max_chars=600)
    assert len(parts) >= 2 and all(len(p) <= 600 for p in parts)


async def test_ocr_scan_to_chunks(tmp_path):
    pdf = tmp_path / "tbmt.pdf"
    pdf.write_bytes(_pdf("Thông báo mời thầu"))
    vision = ScriptedVision({SYS_OCR: {"text": "Thời điểm đóng thầu 09h00 ngày 20/05/2026"}})

    chunks = await ocr_scan_to_chunks(str(pdf), source_doc="tbmt", vision_fn=vision)

    assert chunks and all(c["source_doc"] == "tbmt" for c in chunks)
    c = chunks[0]
    assert "đóng thầu" in c["text"] and c["page_start"] == 1
    assert c["section_path"] == ["Thông báo mời thầu"] and c["node_type"] == "text"
    assert c["chunk_id"].startswith("tbmt-")
    # tương thích index: chỉ cần chunk_id + text; source_doc/page vào metadata
    from experiment.index.schema import chunk_to_node, keep_for_index
    assert keep_for_index(c) is True
    node = chunk_to_node(c)
    assert node.metadata["source_doc"] == "tbmt" and node.text == c["text"]
