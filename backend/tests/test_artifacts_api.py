"""Test endpoint danh mục loại hồ sơ — đồng bộ với CATALOG backend."""
from services import artifact_catalog


def test_list_artifacts_matches_catalog(client):
    r = client.get("/api/v1/artifacts")
    assert r.status_code == 200
    data = r.json()["data"]
    codes = [a["value"] for a in data]
    assert codes == artifact_catalog.all_codes()  # đủ & đúng thứ tự
    first = data[0]
    assert {"value", "label", "nhom", "mo_ta"} <= first.keys()
    assert first["value"] == "don_du_thau" and first["label"]
