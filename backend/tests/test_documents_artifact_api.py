"""Tests cho document upload router — artifact_type + validate (TDD Task 9)."""
import fitz
from services import ai_client


def _pdf(t):
    d = fitz.open(); d.new_page().insert_htmlbox(fitz.Rect(72, 72, 500, 200), f"<p>{t}</p>"); return d.tobytes()


def test_upload_hsdt_with_artifact_validation(client, monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)
    p = client.post("/api/v1/packages", json={"ma_so": "G-A", "ten": "g", "vendors": ["A"]}).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]
    files = {"file": ("bl.pdf", _pdf("THƯ BẢO LÃNH dự thầu ngân hàng ABC giá trị lớn"), "application/pdf")}
    r = client.post(f"/api/v1/packages/{pid}/documents", files=files,
                    data={"loai": "HSDT", "vendor_id": str(vid), "artifact_type": "bao_dam_du_thau"})
    doc = r.json()["data"]
    assert doc["artifact_type"] == "bao_dam_du_thau"
    assert doc["artifact_validation"]["match"] is True
