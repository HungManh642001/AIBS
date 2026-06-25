import pytest
from services import ai_client


@pytest.mark.asyncio
async def test_mock_fallback_when_mock_enabled(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)
    out = await ai_client.ai_json("sys", "prompt", mock_key="eval_legality")
    assert out["_model"] == "mock"
    assert out["result"] in {"PASS", "FAIL", "PARTIAL"}
    assert "evidence" in out


@pytest.mark.asyncio
async def test_falls_back_on_litellm_error(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)

    def boom(*a, **k):
        raise RuntimeError("proxy down")

    monkeypatch.setattr(ai_client, "_litellm_completion", boom)
    out = await ai_client.ai_json("sys", "p", mock_key="extract_criteria")
    assert out["_model"] == "mock"
    assert isinstance(out["criteria"], list)
