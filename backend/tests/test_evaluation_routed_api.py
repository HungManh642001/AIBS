"""Tests cho evaluation router (Task 11 TDD): artifact routing + sub-check results."""
import fitz
from services import ai_client


def _pdf(t):
    d = fitz.open(); d.new_page().insert_htmlbox(fitz.Rect(72, 72, 500, 200), f"<p>{t}</p>"); return d.tobytes()


def _setup(client):
    p = client.post("/api/v1/packages", json={"ma_so": "G-E", "ten": "g", "vendors": ["A"]}).json()["data"]
    pid, vid = p["id"], p["vendors"][0]["id"]
    client.post(f"/api/v1/packages/{pid}/documents",
                files={"file": ("hsmt.pdf", _pdf("Tiêu chuẩn đánh giá hợp lệ; Bảng dữ liệu đấu thầu"), "application/pdf")},
                data={"loai": "HSMT"})
    # HSDT: file bảo đảm dự thầu giá trị đạt ngưỡng
    client.post(f"/api/v1/packages/{pid}/documents",
                files={"file": ("bl.pdf", _pdf("Thư bảo lãnh dự thầu giá trị 200.000.000 đồng hiệu lực 150 ngày"), "application/pdf")},
                data={"loai": "HSDT", "vendor_id": str(vid), "artifact_type": "bao_dam_du_thau"})
    # HSDT: đơn dự thầu
    client.post(f"/api/v1/packages/{pid}/documents",
                files={"file": ("don.pdf", _pdf("Đơn dự thầu có chữ ký và đóng dấu hợp lệ"), "application/pdf")},
                data={"loai": "HSDT", "vendor_id": str(vid), "artifact_type": "don_du_thau"})
    return pid, vid


def test_evaluate_routed_with_subresults(client, monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)
    pid, vid = _setup(client)
    client.post(f"/api/v1/packages/{pid}/de-cuong")          # tạo đề cương từ HSMT (mock)
    client.post(f"/api/v1/packages/{pid}/de-cuong/confirm")
    ev = client.post(f"/api/v1/packages/{pid}/evaluate").json()["data"]
    v = ev["vendors"][0]
    assert v["completeness"]["percent"] >= 0
    bdt = next(c for c in v["criteria"] if c["criteria_ten"] == "Bảo đảm dự thầu")
    assert bdt["result"] == "PASS"

    res = client.get(f"/api/v1/packages/{pid}/results").json()["data"]
    vr = res["vendors"][0]
    assert "completeness" in vr and "percent" in vr["completeness"] and "missing" in vr["completeness"]
    crit = next(c for c in vr["criteria"] if c["criteria_ten"] == "Bảo đảm dự thầu")
    assert len(crit["sub_results"]) >= 2
    assert any("Giá trị" in s["sub_check_ten"] for s in crit["sub_results"])
