def test_health_returns_envelope(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"success": True, "data": {"status": "up"}, "error": None}
