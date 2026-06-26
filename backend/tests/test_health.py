def test_health_returns_envelope(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True and body["error"] is None
    assert body["data"]["status"] == "up"
    assert body["data"]["ai_mode"] in {"mock", "real"}
    assert "ai_model" in body["data"]
