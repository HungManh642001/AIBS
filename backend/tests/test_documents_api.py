"""Tests cho document upload router (TDD Task 14)."""
import fitz


def _text_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    # insert_htmlbox hỗ trợ Unicode/tiếng Việt đúng chuẩn (tránh corrupt diacritics)
    page.insert_htmlbox(fitz.Rect(72, 72, 500, 200), f"<p>{text}</p>")
    return doc.tobytes()


def test_upload_hsmt_extracts_text(client):
    pid = client.post("/api/v1/packages", json={"ma_so": "G-1", "ten": "G"}).json()["data"]["id"]
    files = {"file": ("hsmt.pdf", _text_pdf("Tiêu chí đánh giá hợp lệ kỹ thuật"), "application/pdf")}
    r = client.post(f"/api/v1/packages/{pid}/documents", files=files, data={"loai": "HSMT"})
    assert r.status_code == 200
    doc = r.json()["data"]
    assert doc["trang_thai_ocr"] == "hoan_thanh"
    assert doc["file_kind"] == "pdf_text"

    lst = client.get(f"/api/v1/packages/{pid}/documents").json()["data"]
    assert len(lst) == 1
