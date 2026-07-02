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
    r = client.post(f"/api/v1/packages/{pid}/vendors", json={"ten": "Công ty B", "ma_so_thue": "123"})
    assert r.status_code == 200
    vendors = r.json()["data"]["vendors"]
    assert len(vendors) == 2 and any(v["ten"] == "Công ty B" for v in vendors)


def test_add_vendor_empty_name_400(client):
    pid = client.post("/api/v1/packages", json={"ma_so": "G-VE", "ten": "g"}).json()["data"]["id"]
    r = client.post(f"/api/v1/packages/{pid}/vendors", json={"ten": "  "})
    assert r.status_code == 400


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
