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

    Đo bằng chính triệu chứng cần chứng minh, KHÔNG bằng đồng hồ (đồng hồ chập chờn theo tải máy:
    asyncio.to_thread khởi tạo ThreadPoolExecutor ở lần dùng đầu trong tiến trình, chi phí đó có
    thể ăn hết biên thời gian mà không phải do code hỏng).

    Hàm giả CHẶN THẬT SỰ cho tới khi đủ 2 luồng cùng vào (threading.Barrier) rồi mới nhả. Nếu event
    loop bị chẹn thì call thứ hai không bao giờ vào kịp trong lúc call đầu đang giữ luồng ->
    barrier hết hạn -> BrokenBarrierError, đỏ rõ ràng, không phụ thuộc tốc độ máy.
    """
    import asyncio
    import threading

    import config
    from services import ai_client

    # Phải >= 2: nếu chỉ 1, CHÍNH cổng song song sẽ tuần tự hoá hai call -> barrier timeout vì lý
    # do sai (cổng hẹp), không phải vì event loop bị chẹn.
    monkeypatch.setenv("ABES_AI_SONG_SONG", "4")
    config.get_settings.cache_clear()
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)

    dang_bay = 0
    dinh = 0
    khoa = threading.Lock()
    rao = threading.Barrier(2, timeout=5)   # hàm giả chạy TRONG thread do to_thread bọc

    def cham(system, prompt, max_tokens=None):
        nonlocal dang_bay, dinh
        with khoa:
            dang_bay += 1
            dinh = max(dinh, dang_bay)
        rao.wait()                          # chặn tới khi ĐỦ 2 luồng cùng vào -> chồng lấn thật
        with khoa:
            dang_bay -= 1
        return '{"ok": 1}'

    monkeypatch.setattr(ai_client, "_litellm_completion", cham)
    await asyncio.gather(ai_client.ai_call("s", "p", mock_key="k"),
                         ai_client.ai_call("s", "p2", mock_key="k"))
    assert dinh == 2, f"đỉnh đồng thời = {dinh} — vẫn đang tuần tự, call LLM đang chẹn event loop"
