"""Test F01 - Package management API."""


def test_create_and_get_package(client):
    payload = {"ma_so": "G-100", "ten": "Mua sắm thiết bị",
               "gia_tri_uoc_tinh": 5_000_000_000, "vendors": ["Công ty A", "Công ty B"]}
    r = client.post("/api/v1/packages", json=payload)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["ma_so"] == "G-100" and len(data["vendors"]) == 2
    pid = data["id"]

    g = client.get(f"/api/v1/packages/{pid}").json()["data"]
    assert g["ten"] == "Mua sắm thiết bị"


def test_list_filter_by_trang_thai(client):
    client.post("/api/v1/packages", json={"ma_so": "G-200", "ten": "Gói X"})
    r = client.get("/api/v1/packages?trang_thai=khoi_tao")
    assert r.json()["success"] is True
    assert any(p["ma_so"] == "G-200" for p in r.json()["data"])


def test_delete_package(client):
    pid = client.post("/api/v1/packages", json={
        "ma_so": "G-DEL", "ten": "Gói xóa", "vendors": ["Công ty A"]}).json()["data"]["id"]
    r = client.delete(f"/api/v1/packages/{pid}")
    assert r.status_code == 200 and r.json()["data"]["deleted"] is True
    assert client.get(f"/api/v1/packages/{pid}").status_code == 404
    assert all(p["id"] != pid for p in client.get("/api/v1/packages").json()["data"])


def test_delete_package_not_found(client):
    r = client.delete("/api/v1/packages/99999")
    assert r.status_code == 404


def test_add_vendor_to_package(client):
    pid = client.post("/api/v1/packages", json={
        "ma_so": "G-V", "ten": "Gói V", "vendors": ["Công ty A"]}).json()["data"]["id"]
    r = client.post(f"/api/v1/packages/{pid}/vendors",
                    json={"ten": "Công ty B", "ten_viet_tat": "CtyB", "hinh_thuc": "doc_lap"})
    assert r.status_code == 200
    vendors = r.json()["data"]["vendors"]
    assert len(vendors) == 2
    vb = next(v for v in vendors if v["ten"] == "Công ty B")
    assert vb["ten_viet_tat"] == "CtyB" and vb["hinh_thuc"] == "doc_lap"


def test_add_vendor_empty_name_400(client):
    pid = client.post("/api/v1/packages", json={"ma_so": "G-VE", "ten": "g"}).json()["data"]["id"]
    r = client.post(f"/api/v1/packages/{pid}/vendors", json={"ten": "  "})
    assert r.status_code == 400


def test_patch_vendor_updates_hinh_thuc_and_mst(client):
    pid = client.post("/api/v1/packages", json={
        "ma_so": "G-PV", "ten": "g", "vendors": ["Công ty A"]}).json()["data"]
    vid = pid["vendors"][0]["id"]
    pid = pid["id"]
    r = client.patch(f"/api/v1/packages/{pid}/vendors/{vid}",
                     json={"hinh_thuc": "lien_danh", "ten_viet_tat": "LD-ABC"})
    assert r.status_code == 200
    v = next(x for x in r.json()["data"]["vendors"] if x["id"] == vid)
    assert v["hinh_thuc"] == "lien_danh" and v["ten_viet_tat"] == "LD-ABC"


def test_patch_vendor_partial_keeps_other_fields(client):
    """PATCH chỉ field gửi lên; field không gửi giữ nguyên (đổi hình thức không xóa tên viết tắt)."""
    p = client.post("/api/v1/packages", json={"ma_so": "G-PV2", "ten": "g"}).json()["data"]
    vid = client.post(f"/api/v1/packages/{p['id']}/vendors",
                      json={"ten": "B", "ten_viet_tat": "CtyB"}).json()["data"]["vendors"][0]["id"]
    client.patch(f"/api/v1/packages/{p['id']}/vendors/{vid}", json={"hinh_thuc": "doc_lap"})
    r = client.get(f"/api/v1/packages/{p['id']}")
    v = next(x for x in r.json()["data"]["vendors"] if x["id"] == vid)
    assert v["hinh_thuc"] == "doc_lap" and v["ten_viet_tat"] == "CtyB"


def test_patch_vendor_404(client):
    pid = client.post("/api/v1/packages", json={"ma_so": "G-PV3", "ten": "g"}).json()["data"]["id"]
    r = client.patch(f"/api/v1/packages/{pid}/vendors/99999", json={"hinh_thuc": "doc_lap"})
    assert r.status_code == 404


def test_delete_vendor_cascades(client):
    """Xóa nhà thầu -> dọn tài liệu + kết quả đánh giá của nó; nhà thầu khác còn nguyên."""
    import fitz
    import database as _db, models
    p = client.post("/api/v1/packages",
                    json={"ma_so": "G-DV", "ten": "g", "vendors": ["A", "B"]}).json()["data"]
    pid, va, vb = p["id"], p["vendors"][0]["id"], p["vendors"][1]["id"]
    d = fitz.open(); d.new_page().insert_text((72, 72), "đơn")
    client.post(f"/api/v1/packages/{pid}/documents",
                files={"file": ("don.pdf", d.tobytes(), "application/pdf")},
                data={"loai": "HSDT", "vendor_id": str(va), "artifact_type": "don_du_thau"})
    # seed 1 kết quả đánh giá cho nhà thầu A
    sess = _db.SessionLocal()
    sess.add(models.HsdtCriterionEval(package_id=pid, vendor_id=va, thu_tu=0, nhom="hop_le",
                                      ten="X", ket_qua="đạt", loai=False))
    sess.add(models.HsdtVendorEval(package_id=pid, vendor_id=va, hinh_thuc="độc lập"))
    sess.commit(); sess.close()

    r = client.delete(f"/api/v1/packages/{pid}/vendors/{va}")
    assert r.status_code == 200
    vendors = r.json()["data"]["vendors"]
    assert [v["id"] for v in vendors] == [vb]                          # A biến mất, B còn
    assert client.get(f"/api/v1/packages/{pid}/documents").json()["data"] == []   # tài liệu A dọn sạch
    sess = _db.SessionLocal()
    assert sess.query(models.HsdtCriterionEval).filter_by(vendor_id=va).count() == 0
    assert sess.query(models.HsdtVendorEval).filter_by(vendor_id=va).count() == 0
    sess.close()


def test_delete_vendor_404(client):
    pid = client.post("/api/v1/packages", json={"ma_so": "G-DV4", "ten": "g"}).json()["data"]["id"]
    assert client.delete(f"/api/v1/packages/{pid}/vendors/99999").status_code == 404


def test_delete_package_removes_hsdt_verdicts(client):
    """Xóa gói phải dọn HsdtCriterionEval + HsdtVerdict (FK package_id, ngoài cascade)."""
    import database as _db
    import models
    pid = client.post("/api/v1/packages", json={
        "ma_so": "G-HV", "ten": "g", "vendors": ["A"]}).json()["data"]
    package_id, vendor_id = pid["id"], pid["vendors"][0]["id"]
    sess = _db.SessionLocal()
    ev = models.HsdtCriterionEval(package_id=package_id, vendor_id=vendor_id, ten="X", ket_qua="đạt")
    ev.verdicts.append(models.HsdtVerdict(noi_dung_kiem_tra="n", ket_qua="đạt"))
    sess.add(ev)
    sess.commit()
    sess.close()

    assert client.delete(f"/api/v1/packages/{package_id}").status_code == 200
    check = _db.SessionLocal()
    try:
        assert check.query(models.HsdtCriterionEval).filter_by(package_id=package_id).count() == 0
        assert check.query(models.HsdtVerdict).count() == 0
    finally:
        check.close()
