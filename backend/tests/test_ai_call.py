import pytest
from services import ai_client


@pytest.mark.asyncio
async def test_mock_returns_ok_outcome(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)
    out = await ai_client.ai_call("sys", "p", mock_key="eval_subcheck")
    assert out.status == "ok"
    assert out.model == "mock"
    assert out.data["result"] in {"PASS", "FAIL", "PARTIAL"}


@pytest.mark.asyncio
async def test_real_parse_failure_retries_then_errors(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)
    calls = {"n": 0}

    def garbage(*a, **k):
        calls["n"] += 1
        return "đây không phải JSON"

    monkeypatch.setattr(ai_client, "_litellm_completion", garbage)
    out = await ai_client.ai_call("sys", "p", mock_key="eval_subcheck")
    assert out.status == "error"
    assert out.data is None
    assert calls["n"] == 2   # initial + 1 retry
    assert out.model != "mock"


@pytest.mark.asyncio
async def test_real_success_parses_fenced_json(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)
    monkeypatch.setattr(ai_client, "_litellm_completion",
                        lambda *a, **k: 'Suy luận...\n```json\n{"result":"PASS","evidence":"ok","page_ref":[1]}\n```')
    out = await ai_client.ai_call("sys", "p", mock_key="eval_subcheck")
    assert out.status == "ok"
    assert out.data["result"] == "PASS"


@pytest.mark.asyncio
async def test_validate_failure_becomes_error(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)
    monkeypatch.setattr(ai_client, "_litellm_completion",
                        lambda *a, **k: '{"result":"PASS"}')   # thiếu evidence

    def validate(d):
        if "evidence" not in d:
            raise ValueError("thiếu evidence")
        return d

    out = await ai_client.ai_call("sys", "p", mock_key="eval_subcheck", validate=validate)
    assert out.status == "error"
