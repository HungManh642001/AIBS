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
