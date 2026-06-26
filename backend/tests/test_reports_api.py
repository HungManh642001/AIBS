"""Tests cho report router (TDD Task 16): sinh và tải báo cáo Word/Excel."""
import io

import fitz
from docx import Document
from openpyxl import Workbook

from services import ai_client


def _text_pdf(t: str) -> bytes:
    d = fitz.open()
    d.new_page().insert_htmlbox(fitz.Rect(72, 72, 500, 200), f"<p>{t}</p>")
    return d.tobytes()


def _setup(client, monkeypatch):
    """Tạo gói thầu, upload HSMT + HSDT, tạo đề cương, chạy đánh giá."""
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)
    p = client.post(
        "/api/v1/packages",
        json={"ma_so": "G-R", "ten": "G", "vendors": ["A"]},
    ).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]
    client.post(
        f"/api/v1/packages/{pid}/documents",
        files={"file": ("h.pdf", _text_pdf("Tiêu chí đánh giá hợp lệ kỹ thuật"), "application/pdf")},
        data={"loai": "HSMT"},
    )
    client.post(
        f"/api/v1/packages/{pid}/documents",
        files={"file": ("d.pdf", _text_pdf("Hồ sơ dự thầu của nhà thầu A"), "application/pdf")},
        data={"loai": "HSDT", "vendor_id": str(vid)},
    )
    # Tạo và chốt đề cương trước khi evaluate (yêu cầu bắt buộc trong luồng mới)
    client.post(f"/api/v1/packages/{pid}/de-cuong")
    client.post(f"/api/v1/packages/{pid}/de-cuong/confirm")
    client.post(f"/api/v1/packages/{pid}/evaluate")
    return pid


def test_generate_and_download_word(client, monkeypatch):
    pid = _setup(client, monkeypatch)

    gen = client.post(f"/api/v1/packages/{pid}/reports?loai=word").json()["data"]
    assert gen["report_id"]

    dl = client.get(f"/api/v1/reports/{gen['report_id']}/download")
    assert dl.status_code == 200
    assert len(dl.content) > 0


def test_generate_and_download_excel(client, monkeypatch):
    pid = _setup(client, monkeypatch)

    gen = client.post(f"/api/v1/packages/{pid}/reports?loai=excel").json()["data"]
    assert gen["report_id"]
    assert gen["loai"] == "excel"

    dl = client.get(f"/api/v1/reports/{gen['report_id']}/download")
    assert dl.status_code == 200
    assert len(dl.content) > 0


def test_generate_report_missing_package(client):
    r = client.post("/api/v1/packages/99999/reports?loai=word")
    assert r.status_code == 404


def test_download_missing_report(client):
    r = client.get("/api/v1/reports/99999/download")
    assert r.status_code == 404


def _price_xlsx() -> bytes:
    """Tạo bảng giá Excel với 1 lỗi số học: 100*2=200 nhưng khai 250."""
    wb = Workbook()
    ws = wb.active
    ws.title = "BangGia"
    ws.append(["STT", "Hạng mục", "Đơn giá", "Số lượng", "Thành tiền"])
    ws.append([1, "Máy chủ", 100, 2, 250])   # sai số học: đúng là 200
    ws.append([2, "Switch", 50, 3, 150])       # đúng
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_financials_persisted_in_report(client, monkeypatch):
    """Kiểm tra rằng dữ liệu đánh giá được persist và sinh được báo cáo Word có nội dung."""
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)

    # Tạo gói thầu với 1 nhà thầu
    p = client.post(
        "/api/v1/packages",
        json={"ma_so": "G-FIN", "ten": "Gói tài chính", "vendors": ["NhaThuauA"]},
    ).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]

    # Upload HSMT
    client.post(
        f"/api/v1/packages/{pid}/documents",
        files={"file": ("h.pdf", _text_pdf("Tiêu chí đánh giá hợp lệ kỹ thuật tài chính"), "application/pdf")},
        data={"loai": "HSMT"},
    )

    # Upload HSDT PDF với artifact_type để routing hop_le tìm được
    client.post(
        f"/api/v1/packages/{pid}/documents",
        files={"file": ("d.pdf", _text_pdf("Đơn dự thầu có chữ ký đóng dấu hợp lệ của nhà thầu A"), "application/pdf")},
        data={"loai": "HSDT", "vendor_id": str(vid), "artifact_type": "don_du_thau"},
    )

    # Upload bảng giá Excel (tham khảo cho tài chính — không xử lý trong evaluate mới)
    client.post(
        f"/api/v1/packages/{pid}/documents",
        files={"file": ("gia.xlsx", _price_xlsx(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"loai": "HSDT", "vendor_id": str(vid)},
    )

    # Tạo và chốt đề cương (bắt buộc trước evaluate)
    client.post(f"/api/v1/packages/{pid}/de-cuong")
    client.post(f"/api/v1/packages/{pid}/de-cuong/confirm")

    # Chạy đánh giá
    ev = client.post(f"/api/v1/packages/{pid}/evaluate").json()
    assert ev["success"], f"evaluate failed: {ev}"

    # Sinh báo cáo Word
    gen = client.post(f"/api/v1/packages/{pid}/reports?loai=word").json()["data"]
    assert gen["report_id"]

    # Tải báo cáo
    dl = client.get(f"/api/v1/reports/{gen['report_id']}/download")
    assert dl.status_code == 200
    assert len(dl.content) > 0

    # Kiểm tra nội dung báo cáo: tên nhà thầu và kết quả đánh giá hợp lệ có mặt
    doc = Document(io.BytesIO(dl.content))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "NhaThuauA" in text, f"Tên nhà thầu không có trong báo cáo. Text:\n{text}"
    assert "Đơn dự thầu hợp lệ" in text, f"Tiêu chí hop_le không có trong báo cáo. Text:\n{text}"
