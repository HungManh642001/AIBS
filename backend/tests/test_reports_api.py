"""Tests cho report router (TDD Task 16): sinh và tải báo cáo Word/Excel."""
import fitz

from services import ai_client


def _text_pdf(t: str) -> bytes:
    d = fitz.open()
    d.new_page().insert_htmlbox(fitz.Rect(72, 72, 500, 200), f"<p>{t}</p>")
    return d.tobytes()


def _setup(client, monkeypatch):
    """Tạo gói thầu, upload HSMT + HSDT, chạy đánh giá."""
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
