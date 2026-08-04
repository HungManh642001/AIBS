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


def _xlsx() -> bytes:
    """File Excel tối thiểu (openpyxl) để thử upload."""
    import io
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.append(["Hạng mục", "Đơn giá"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_upload_excel_bi_tu_choi(client):
    """Excel CHƯA được pipeline đánh giá hỗ trợ -> từ chối ngay, không nhận rồi bỏ qua âm thầm."""
    p = client.post("/api/v1/packages", json={"ma_so": "G-X", "ten": "G", "vendors": ["A"]}).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]
    files = {"file": ("bang_gia.xlsx", _xlsx(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = client.post(f"/api/v1/packages/{pid}/documents", files=files,
                    data={"loai": "HSDT", "vendor_id": str(vid), "artifact_type": "bang_gia"})
    assert r.status_code == 415
    body = r.json()
    assert body["success"] is False
    assert "Excel" in body["error"]
    # Không được tạo bản ghi tài liệu nào.
    assert client.get(f"/api/v1/packages/{pid}/documents").json()["data"] == []


def test_upload_hsdt_thieu_loai_ho_so_bi_tu_choi(client):
    """HSDT không có loại hồ sơ sẽ bị pipeline đánh giá bỏ qua -> chặn ngay từ upload."""
    p = client.post("/api/v1/packages", json={"ma_so": "G-NT", "ten": "G", "vendors": ["A"]}).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]
    files = {"file": ("don.pdf", _text_pdf("Đơn dự thầu"), "application/pdf")}
    r = client.post(f"/api/v1/packages/{pid}/documents", files=files,
                    data={"loai": "HSDT", "vendor_id": str(vid)})
    assert r.status_code == 400
    assert "loại hồ sơ" in r.json()["error"].lower()
    assert client.get(f"/api/v1/packages/{pid}/documents").json()["data"] == []


def test_upload_hsmt_khong_can_loai_ho_so(client):
    """HSMT/TBMT không thuộc danh mục loại hồ sơ HSDT -> vẫn tải được như cũ."""
    pid = client.post("/api/v1/packages", json={"ma_so": "G-HM", "ten": "G"}).json()["data"]["id"]
    files = {"file": ("hsmt.pdf", _text_pdf("Tiêu chí"), "application/pdf")}
    assert client.post(f"/api/v1/packages/{pid}/documents", files=files,
                       data={"loai": "HSMT"}).status_code == 200


def test_upload_giu_loai_ho_so_khi_ocr_loi(client, monkeypatch):
    """OCR lỗi KHÔNG được làm mất loại hồ sơ đã khai — mất là tài liệu bị loại thầm lặng khỏi chấm."""
    import services.documents as sd
    monkeypatch.setattr(sd, "extract_document", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("hỏng")))
    p = client.post("/api/v1/packages", json={"ma_so": "G-OE", "ten": "G", "vendors": ["A"]}).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]
    files = {"file": ("don.pdf", _text_pdf("Đơn dự thầu"), "application/pdf")}
    doc = client.post(f"/api/v1/packages/{pid}/documents", files=files,
                      data={"loai": "HSDT", "vendor_id": str(vid),
                            "artifact_type": "don_du_thau"}).json()["data"]
    assert doc["trang_thai_ocr"].startswith("loi")
    assert doc["artifact_type"] == "don_du_thau"


def test_patch_khong_cho_xoa_trang_loai_ho_so(client):
    """Xóa trắng loại hồ sơ = tài liệu biến mất khỏi đánh giá mà UI vẫn đếm -> chặn."""
    pid, _vid, did = _pkg_with_hsdt(client)
    r = client.patch(f"/api/v1/packages/{pid}/documents/{did}", json={"artifact_type": ""})
    assert r.status_code == 400
    got = client.get(f"/api/v1/packages/{pid}/documents").json()["data"]
    assert got[0]["artifact_type"] == "don_du_thau"   # giữ nguyên giá trị cũ


def _scan_pdf() -> bytes:
    """PDF KHÔNG có text nhúng -> classify_pdf trả 'pdf_scan' (ngưỡng 20 ký tự)."""
    doc = fitz.open()
    doc.new_page()          # trang trắng, không chèn chữ
    return doc.tobytes()


def test_upload_scan_khong_goi_llm_kiem_loai(client, monkeypatch):
    """Bản scan không có text để phán -> gọi LLM là vừa tốn thời gian chờ vừa sinh cảnh báo giả."""
    import routers.documents as rd

    goi = []

    async def spy(pages, declared_type):
        goi.append(declared_type)
        return {"match": False, "suggested_type": "", "confidence": 0.0, "note": "x"}

    monkeypatch.setattr(rd, "validate_artifact", spy)
    p = client.post("/api/v1/packages",
                    json={"ma_so": "G-SC", "ten": "G", "vendors": ["A"]}).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]
    r = client.post(f"/api/v1/packages/{pid}/documents",
                    files={"file": ("scan.pdf", _scan_pdf(), "application/pdf")},
                    data={"loai": "HSDT", "vendor_id": str(vid),
                          "artifact_type": "don_du_thau"})
    assert r.status_code == 200
    doc = r.json()["data"]
    assert doc["file_kind"] == "pdf_scan"
    assert goi == []                              # KHÔNG call LLM nào
    assert doc["artifact_validation"] is None     # để None, KHÔNG bịa kết quả
    assert doc["artifact_type"] == "don_du_thau"  # loại hồ sơ vẫn được ghi


def test_upload_pdf_co_text_van_kiem_loai_nhu_cu(client, monkeypatch):
    """Hồi quy: file có text nhúng vẫn được kiểm loại — đây là ca kiểm thật sự có căn cứ."""
    import routers.documents as rd

    goi = []

    async def spy(pages, declared_type):
        goi.append(declared_type)
        return {"match": True, "suggested_type": "don_du_thau", "confidence": 0.9, "note": "ok"}

    monkeypatch.setattr(rd, "validate_artifact", spy)
    p = client.post("/api/v1/packages",
                    json={"ma_so": "G-TX", "ten": "G", "vendors": ["A"]}).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]
    r = client.post(f"/api/v1/packages/{pid}/documents",
                    files={"file": ("don.pdf", _text_pdf("Đơn dự thầu của nhà thầu"),
                                    "application/pdf")},
                    data={"loai": "HSDT", "vendor_id": str(vid),
                          "artifact_type": "don_du_thau"})
    assert r.status_code == 200
    assert goi == ["don_du_thau"]
    assert r.json()["data"]["artifact_validation"]["match"] is True


def test_doi_loai_ho_so_tren_file_scan_khong_goi_llm(client, monkeypatch):
    """PATCH đổi loại: file scan có extracted_text='[]' -> mỗi lần đổi lại tốn 1 call vô ích."""
    import routers.documents as rd

    p = client.post("/api/v1/packages",
                    json={"ma_so": "G-PT", "ten": "G", "vendors": ["A"]}).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]
    doc_id = client.post(f"/api/v1/packages/{pid}/documents",
                         files={"file": ("scan.pdf", _scan_pdf(), "application/pdf")},
                         data={"loai": "HSDT", "vendor_id": str(vid),
                               "artifact_type": "don_du_thau"}).json()["data"]["id"]

    goi = []

    async def spy(pages, declared_type):
        goi.append(declared_type)
        return {"match": True, "suggested_type": declared_type, "confidence": 0.9, "note": "ok"}

    monkeypatch.setattr(rd, "validate_artifact", spy)
    r = client.patch(f"/api/v1/packages/{pid}/documents/{doc_id}",
                     json={"artifact_type": "bao_dam_du_thau"})
    assert r.status_code == 200
    assert goi == []
    assert r.json()["data"]["artifact_type"] == "bao_dam_du_thau"
    assert r.json()["data"]["artifact_validation"] is None


def test_doi_loai_ho_so_tren_file_co_text_van_kiem_nhu_cu(client, monkeypatch):
    """Hồi quy chiều còn lại: file có text nhúng thì PATCH vẫn kiểm loại như trước."""
    import routers.documents as rd

    p = client.post("/api/v1/packages",
                    json={"ma_so": "G-PX", "ten": "G", "vendors": ["A"]}).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]

    goi = []

    async def spy(pages, declared_type):
        goi.append(declared_type)
        return {"match": True, "suggested_type": declared_type, "confidence": 0.9, "note": "ok"}

    monkeypatch.setattr(rd, "validate_artifact", spy)
    doc_id = client.post(f"/api/v1/packages/{pid}/documents",
                         files={"file": ("don.pdf", _text_pdf("Đơn dự thầu của nhà thầu"),
                                         "application/pdf")},
                         data={"loai": "HSDT", "vendor_id": str(vid),
                               "artifact_type": "don_du_thau"}).json()["data"]["id"]
    goi.clear()                                   # bỏ lần gọi lúc upload, chỉ đo lần PATCH
    r = client.patch(f"/api/v1/packages/{pid}/documents/{doc_id}",
                     json={"artifact_type": "bao_dam_du_thau"})
    assert r.status_code == 200
    assert goi == ["bao_dam_du_thau"]
    assert r.json()["data"]["artifact_validation"]["match"] is True
