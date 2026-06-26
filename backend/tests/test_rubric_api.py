"""Tests cho tiêu chí đánh giá router: extract / edit / confirm."""
import fitz
from services import ai_client


def _pdf(t):
    d = fitz.open()
    d.new_page().insert_htmlbox(fitz.Rect(72, 72, 500, 200), f"<p>{t}</p>")
    return d.tobytes()


def _pkg_with_hsmt(client):
    pid = client.post("/api/v1/packages", json={"ma_so": "G-D", "ten": "g"}).json()["data"]["id"]
    client.post(
        f"/api/v1/packages/{pid}/documents",
        files={"file": ("hsmt.pdf", _pdf("Tiêu chuẩn đánh giá tính hợp lệ và Bảng dữ liệu đấu thầu"), "application/pdf")},
        data={"loai": "HSMT"},
    )
    return pid


def test_extract_edit_confirm_rubric(client, monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)
    pid = _pkg_with_hsmt(client)
    ext = client.post(f"/api/v1/packages/{pid}/rubric").json()["data"]
    assert any(c["ten"] == "Bảo đảm dự thầu" for c in ext["criteria"])
    bdt = next(c for c in ext["criteria"] if c["ten"] == "Bảo đảm dự thầu")
    assert bdt["required_artifacts"] == ["bao_dam_du_thau"]
    assert any(s["check_type"] == "value_threshold" for s in bdt["sub_checks"])

    # chuyên gia sửa: đổi tên một sub-check rồi PUT
    bdt["sub_checks"][0]["ten"] = "Có bảo đảm dự thầu (đã sửa)"
    client.put(f"/api/v1/packages/{pid}/rubric", json={"criteria": ext["criteria"]})
    got = client.get(f"/api/v1/packages/{pid}/rubric").json()["data"]
    bdt2 = next(c for c in got["criteria"] if c["ten"] == "Bảo đảm dự thầu")
    assert bdt2["sub_checks"][0]["ten"] == "Có bảo đảm dự thầu (đã sửa)"

    conf = client.post(f"/api/v1/packages/{pid}/rubric/confirm").json()["data"]
    assert conf["confirmed"] is True
