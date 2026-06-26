"""Tests cho evaluation router (TDD Task 15): đánh giá, kết quả, override."""
import fitz

from services import ai_client


def _text_pdf(t: str) -> bytes:
    d = fitz.open()
    d.new_page().insert_htmlbox(fitz.Rect(72, 72, 500, 200), f"<p>{t}</p>")
    return d.tobytes()


def _setup(client, monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)
    pid = client.post("/api/v1/packages",
                      json={"ma_so": "G-9", "ten": "G", "vendors": ["A"]}).json()["data"]
    package_id = pid["id"]
    vendor_id = pid["vendors"][0]["id"]
    client.post(f"/api/v1/packages/{package_id}/documents",
                files={"file": ("hsmt.pdf",
                                _text_pdf("Tiêu chí đánh giá hợp lệ kỹ thuật năng lực"),
                                "application/pdf")},
                data={"loai": "HSMT"})
    client.post(f"/api/v1/packages/{package_id}/documents",
                files={"file": ("hsdt.pdf",
                                _text_pdf("Hồ sơ dự thầu của nhà thầu A đầy đủ hợp lệ"),
                                "application/pdf")},
                data={"loai": "HSDT", "vendor_id": str(vendor_id), "artifact_type": "don_du_thau"})
    client.post(f"/api/v1/packages/{package_id}/de-cuong")
    client.post(f"/api/v1/packages/{package_id}/de-cuong/confirm")
    return package_id, vendor_id


def test_evaluate_then_results_and_override(client, monkeypatch):
    package_id, vendor_id = _setup(client, monkeypatch)
    ev = client.post(f"/api/v1/packages/{package_id}/evaluate").json()["data"]
    assert ev["vendors"]

    res = client.get(f"/api/v1/packages/{package_id}/results").json()["data"]
    crit = res["vendors"][0]["criteria"][0]
    sub_id = crit["sub_results"][0]["id"]
    ov = client.put(f"/api/v1/evaluation/sub-check-result/{sub_id}/override",
                    json={"ket_qua": "FAIL", "ghi_chu": "Chuyên gia bác bỏ"})
    assert ov.json()["data"]["overridden"] is True


def test_re_evaluate_is_idempotent(client, monkeypatch):
    """Re-evaluate không được tích lũy kết quả orphan từ lần chạy trước."""
    package_id, vendor_id = _setup(client, monkeypatch)
    # Lần đánh giá thứ nhất
    client.post(f"/api/v1/packages/{package_id}/evaluate")
    first = client.get(f"/api/v1/packages/{package_id}/results").json()["data"]
    first_count = sum(len(v["criteria"]) for v in first["vendors"])
    # Lần đánh giá thứ hai — kết quả cũ phải bị xóa trước
    client.post(f"/api/v1/packages/{package_id}/evaluate")
    second = client.get(f"/api/v1/packages/{package_id}/results").json()["data"]
    second_count = sum(len(v["criteria"]) for v in second["vendors"])
    assert first_count > 0, "Phải có ít nhất một kết quả sau lần đánh giá đầu"
    assert second_count == first_count, (
        f"Re-evaluate sinh orphan rows: first={first_count}, second={second_count}"
    )
