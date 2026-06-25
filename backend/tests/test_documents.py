import fitz  # PyMuPDF
from services import documents


def _make_text_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    # insert_htmlbox hỗ trợ Unicode (tiếng Việt) đúng encoding
    page.insert_htmlbox(fitz.Rect(72, 72, 500, 200), f"<p>{text}</p>")
    return doc.tobytes()


def test_classify_text_pdf():
    data = _make_text_pdf("Tiêu chí đánh giá hợp lệ")
    assert documents.classify_pdf(data) == "pdf_text"


def test_extract_text_pdf_returns_pages():
    data = _make_text_pdf("Đơn dự thầu hợp lệ")
    pages = documents.extract_pdf(data)
    assert pages[0]["page"] == 1
    assert "Đơn dự thầu" in pages[0]["text"]
