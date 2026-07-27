"""Tests router tiêu chí (pipeline decompose): bóc / sửa / chốt. Pipeline được mock (không cần proxy)."""
import fitz


def _pdf(t):
    d = fitz.open()
    d.new_page().insert_htmlbox(fitz.Rect(72, 72, 500, 200), f"<p>{t}</p>")
    return d.tobytes()


def _pkg_with_hsmt(client):
    pid = client.post("/api/v1/packages", json={"ma_so": "G-D", "ten": "g"}).json()["data"]["id"]
    client.post(
        f"/api/v1/packages/{pid}/documents",
        files={"file": ("hsmt.pdf", _pdf("Tiêu chuẩn đánh giá tính hợp lệ"), "application/pdf")},
        data={"loai": "HSMT"},
    )
    return pid


# decomposition.json giả lập (thay chuỗi extract+chunk+index+decompose cần proxy).
_FAKE_DECOMP = {
    "doc": "HSMT", "groups": [{"group": "hop_le", "criteria": [{
        "nhom": "hop_le", "ten": "Bảo đảm dự thầu", "yeu_cau_goc": "Giá trị, hiệu lực theo E-HSMT",
        "hsdt_can_kiem_tra": ["bao_dam_du_thau"],
        "noi_dung_can_kiem_tra": [
            {"noi_dung_kiem_tra": "Giá trị bảo lãnh", "hsdt_kiem_tra": "bao_dam_du_thau",
             "yeu_cau": "Thỏa mãn giá trị bảo lãnh", "can_lam_ro": "Giá trị bảo lãnh",
             "can_tra_cuu": True, "thong_tin_bo_sung": "6.100.000 VNĐ", "nguon": "E-BDL 18.2",
             "can_review": False}]}]}],
    "summary": {"n_groups": 1, "n_criteria": 1},
}


def _mock_pipeline(monkeypatch, decomp=_FAKE_DECOMP, captured=None):
    import routers.rubric as rr

    async def _fake(pdf_path, workdir, scan_sources=None):
        if captured is not None:
            captured["scan_sources"] = scan_sources
        return decomp
    monkeypatch.setattr(rr, "build_decomposition", _fake)


def test_extract_passes_tbmt_as_scan_source(client, monkeypatch):
    """TBMT đã upload -> router gom thành scan_source (source_doc, đường dẫn) truyền vào pipeline."""
    cap: dict = {}
    _mock_pipeline(monkeypatch, captured=cap)
    pid = _pkg_with_hsmt(client)
    client.post(f"/api/v1/packages/{pid}/documents",
                files={"file": ("tbmt.pdf", _pdf("Thời điểm đóng thầu 09:00 14/07/2026"), "application/pdf")},
                data={"loai": "TBMT"})
    client.post(f"/api/v1/packages/{pid}/rubric")

    scan = cap["scan_sources"]
    assert len(scan) == 1
    source_doc, path = scan[0]
    assert "mời thầu" in source_doc.lower() and path.endswith(".pdf")


def test_extract_no_tbmt_empty_scan_sources(client, monkeypatch):
    cap: dict = {}
    _mock_pipeline(monkeypatch, captured=cap)
    pid = _pkg_with_hsmt(client)
    client.post(f"/api/v1/packages/{pid}/rubric")
    assert cap["scan_sources"] == []


def test_rubric_persists_ap_dung(client, monkeypatch):
    """ap_dung (áp dụng độc lập/liên danh cấp nội dung) lưu & đọc lại được, qua cả PUT chuyên gia sửa."""
    decomp = {"doc": "HSMT", "groups": [{"group": "hop_le", "criteria": [{
        "nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ", "yeu_cau_goc": "…",
        "hsdt_can_kiem_tra": ["don_du_thau", "thoa_thuan_lien_danh"],
        "noi_dung_can_kiem_tra": [
            {"noi_dung_kiem_tra": "Đơn ký hợp pháp", "hsdt_kiem_tra": "don_du_thau",
             "yeu_cau": "ký hợp pháp", "can_lam_ro": "", "can_tra_cuu": False,
             "thong_tin_bo_sung": "", "nguon": "", "can_review": False, "ap_dung": ""},
            {"noi_dung_kiem_tra": "Liên danh ký theo phân công", "hsdt_kiem_tra": "don_du_thau",
             "yeu_cau": "phân công", "can_lam_ro": "", "can_tra_cuu": False,
             "thong_tin_bo_sung": "", "nguon": "", "can_review": False, "ap_dung": "lien_danh"}]}]}],
        "summary": {"n_groups": 1, "n_criteria": 1}}
    _mock_pipeline(monkeypatch, decomp=decomp)
    pid = _pkg_with_hsmt(client)
    got = client.post(f"/api/v1/packages/{pid}/rubric").json()["data"]
    nds = got["criteria"][0]["noi_dung_can_kiem_tra"]
    assert [n["ap_dung"] for n in nds] == ["", "lien_danh"]

    # chuyên gia PUT lại (sửa ap_dung) -> vẫn giữ
    nds[0]["ap_dung"] = "doc_lap"
    client.put(f"/api/v1/packages/{pid}/rubric", json={"criteria": got["criteria"]})
    got2 = client.get(f"/api/v1/packages/{pid}/rubric").json()["data"]
    assert got2["criteria"][0]["noi_dung_can_kiem_tra"][0]["ap_dung"] == "doc_lap"


def test_extract_edit_confirm_rubric(client, monkeypatch):
    _mock_pipeline(monkeypatch)
    pid = _pkg_with_hsmt(client)

    ext = client.post(f"/api/v1/packages/{pid}/rubric").json()["data"]
    bdt = next(c for c in ext["criteria"] if c["ten"] == "Bảo đảm dự thầu")
    assert bdt["hsdt_can_kiem_tra"] == ["bao_dam_du_thau"]
    nd = bdt["noi_dung_can_kiem_tra"][0]
    assert nd["thong_tin_bo_sung"] == "6.100.000 VNĐ" and nd["nguon"] == "E-BDL 18.2"

    # chuyên gia sửa 1 nội dung rồi PUT
    bdt["noi_dung_can_kiem_tra"][0]["thong_tin_bo_sung"] = "6.100.000 VNĐ (đã sửa)"
    client.put(f"/api/v1/packages/{pid}/rubric", json={"criteria": ext["criteria"]})
    got = client.get(f"/api/v1/packages/{pid}/rubric").json()["data"]
    bdt2 = next(c for c in got["criteria"] if c["ten"] == "Bảo đảm dự thầu")
    assert bdt2["noi_dung_can_kiem_tra"][0]["thong_tin_bo_sung"] == "6.100.000 VNĐ (đã sửa)"

    conf = client.post(f"/api/v1/packages/{pid}/rubric/confirm").json()["data"]
    assert conf["confirmed"] is True


def test_extract_without_hsmt_returns_400(client):
    pid = client.post("/api/v1/packages", json={"ma_so": "G-N", "ten": "n"}).json()["data"]["id"]
    r = client.post(f"/api/v1/packages/{pid}/rubric")
    assert r.status_code == 400
    assert "hsmt" in r.json()["error"].lower()


def test_extract_pipeline_error_returns_502(client, monkeypatch):
    import routers.rubric as rr

    async def _boom(pdf_path, workdir, scan_sources=None):
        raise RuntimeError("proxy down")
    monkeypatch.setattr(rr, "build_decomposition", _boom)
    pid = _pkg_with_hsmt(client)
    r = client.post(f"/api/v1/packages/{pid}/rubric")
    assert r.status_code == 502
    assert "proxy down" in r.json()["error"]


def test_loi_ai_khong_mat_khi_chuyen_gia_luu(client):
    """GET phải trả loi_ai, nếu không PUT round-trip sẽ ghi đè thành rỗng.

    Ghi chú lỗi AI của tiêu chí là dấu vết để chuyên gia biết chỗ nào máy không chắc — mất nó ngay
    lần sửa đầu tiên thì coi như không có.
    """
    import models
    import database as _db

    pid = client.post("/api/v1/packages", json={"ma_so": "G-LA", "ten": "g"}).json()["data"]["id"]
    sess = _db.SessionLocal()
    sess.add(models.RubricCriterion(
        package_id=pid, thu_tu=0, nhom="hop_le", ten="Đơn dự thầu", yeu_cau_goc="Có đơn",
        hsdt_can_kiem_tra=["don_du_thau"], loi_ai="Không tra được mốc đóng thầu"))
    sess.commit()
    sess.close()

    got = client.get(f"/api/v1/packages/{pid}/rubric").json()["data"]["criteria"]
    assert got[0]["loi_ai"] == "Không tra được mốc đóng thầu"

    # Chuyên gia sửa tên rồi Lưu -> loi_ai phải còn.
    got[0]["ten"] = "Đơn dự thầu (đã sửa)"
    client.put(f"/api/v1/packages/{pid}/rubric", json={"criteria": got})
    after = client.get(f"/api/v1/packages/{pid}/rubric").json()["data"]["criteria"]
    assert after[0]["ten"] == "Đơn dự thầu (đã sửa)"
    assert after[0]["loi_ai"] == "Không tra được mốc đóng thầu"
