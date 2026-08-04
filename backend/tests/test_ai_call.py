import pytest
from services import ai_client


@pytest.mark.asyncio
async def test_mock_returns_ok_outcome(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)
    out = await ai_client.ai_call("sys", "p", mock_key="validate_artifact")
    assert out.status == "ok"
    assert out.model == "mock"
    assert out.data["match"] is True


@pytest.mark.asyncio
async def test_mock_key_khong_ton_tai_tra_error(monkeypatch):
    """no-silent-mock: mock thiếu dữ liệu -> error, KHÔNG bịa payload sai schema."""
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)
    out = await ai_client.ai_call("sys", "p", mock_key="khong_co_that")
    assert out.status == "error"
    assert out.data is None
    assert "khong_co_that" in out.error


@pytest.mark.asyncio
async def test_real_parse_failure_retries_then_errors(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)
    calls = {"n": 0}

    def garbage(*a, **k):
        calls["n"] += 1
        return "đây không phải JSON"

    monkeypatch.setattr(ai_client, "_litellm_completion", garbage)
    out = await ai_client.ai_call("sys", "p", mock_key="validate_artifact")
    assert out.status == "error"
    assert out.data is None
    assert calls["n"] == 2   # initial + 1 retry
    assert out.model != "mock"


@pytest.mark.asyncio
async def test_real_success_parses_fenced_json(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)
    monkeypatch.setattr(ai_client, "_litellm_completion",
                        lambda *a, **k: 'Suy luận...\n```json\n{"result":"PASS","evidence":"ok","page_ref":[1]}\n```')
    out = await ai_client.ai_call("sys", "p", mock_key="validate_artifact")
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

    out = await ai_client.ai_call("sys", "p", mock_key="validate_artifact", validate=validate)
    assert out.status == "error"


async def test_ai_call_khong_chen_event_loop(monkeypatch):
    """Call LLM đồng bộ nằm trong async def sẽ chẹn loop -> mọi gather thành tuần tự.

    Đo bằng chính triệu chứng: hai call chạy chồng nhau thì tổng thời gian phải xấp xỉ MỘT call,
    không phải hai.
    """
    import asyncio
    import time

    import config
    from services import ai_client

    monkeypatch.setenv("ABES_AI_SONG_SONG", "4")
    config.get_settings.cache_clear()
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)

    def cham(system, prompt, max_tokens=None):
        time.sleep(0.20)                      # ĐỒNG BỘ, đúng như litellm.completion
        return '{"ok": 1}'

    monkeypatch.setattr(ai_client, "_litellm_completion", cham)
    t0 = time.perf_counter()
    await asyncio.gather(ai_client.ai_call("s", "p", mock_key="k"),
                         ai_client.ai_call("s", "p2", mock_key="k"))
    trong = time.perf_counter() - t0
    assert trong < 0.35, f"hai call mất {trong:.2f}s — vẫn đang tuần tự"
