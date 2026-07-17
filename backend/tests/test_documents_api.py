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
    assert lst[0]["file_name"] == "hsmt.pdf"


def _pkg_with_hsdt(client) -> tuple[int, int, int]:
    p = client.post("/api/v1/packages", json={"ma_so": "G-D", "ten": "G", "vendors": ["A"]}).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]
    files = {"file": ("don.pdf", _text_pdf("Đơn dự thầu của nhà thầu"), "application/pdf")}
    doc = client.post(f"/api/v1/packages/{pid}/documents", files=files,
                      data={"loai": "HSDT", "vendor_id": str(vid),
                            "artifact_type": "don_du_thau"}).json()["data"]
    return pid, vid, doc["id"]


def test_delete_document(client):
    pid, _vid, did = _pkg_with_hsdt(client)
    r = client.delete(f"/api/v1/packages/{pid}/documents/{did}")
    assert r.status_code == 200
    assert client.get(f"/api/v1/packages/{pid}/documents").json()["data"] == []


def test_delete_document_404_other_package(client):
    pid, _vid, did = _pkg_with_hsdt(client)
    other = client.post("/api/v1/packages", json={"ma_so": "G-O", "ten": "o"}).json()["data"]["id"]
    assert client.delete(f"/api/v1/packages/{other}/documents/{did}").status_code == 404


def test_patch_document_type_recomputes_validation(client):
    pid, _vid, did = _pkg_with_hsdt(client)
    r = client.patch(f"/api/v1/packages/{pid}/documents/{did}",
                     json={"artifact_type": "bao_dam_du_thau"})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["artifact_type"] == "bao_dam_du_thau"
    assert d["artifact_validation"] is not None      # đã tính lại cảnh báo nghi-nhầm-loại
