"""Tham số sinh phải cố định — cùng đầu vào thì model phải cho cùng đầu ra.

temperature=0 KHÔNG đủ: vLLM gộp batch động nên thứ tự cộng số thực đổi theo tải, greedy vẫn ra
khác nhau. `seed` là điều kiện tối thiểu để tái lập.
"""
import config


def _bat(monkeypatch) -> list[dict]:
    """Bắt tham số truyền vào litellm.completion (không gọi mạng)."""
    goi: list[dict] = []

    class _FakeLitellm:
        @staticmethod
        def completion(**kw):
            goi.append(kw)
            return {"choices": [{"message": {"content": '```json\n{"ok":1}\n```'},
                                 "finish_reason": "stop"}]}

    import sys
    monkeypatch.setitem(sys.modules, "litellm", _FakeLitellm)
    monkeypatch.setattr(config, "get_settings", config.get_settings)
    config.get_settings.cache_clear()
    return goi


def test_ai_call_truyen_seed_va_top_p(monkeypatch):
    from services.ai_client import _litellm_completion

    goi = _bat(monkeypatch)
    monkeypatch.setenv("ABES_AI_MOCK", "false")
    config.get_settings.cache_clear()
    _litellm_completion("sys", "prompt")

    assert goi, "phải gọi litellm"
    kw = goi[-1]
    assert kw["temperature"] == 0.0
    assert kw["seed"] == config.get_settings().ai_seed
    assert kw["top_p"] == 1.0


async def test_vision_truyen_seed_va_top_p(monkeypatch):
    from experiment.evaluate.vision import default_vision_fn

    goi = _bat(monkeypatch)
    monkeypatch.setenv("ABES_AI_MOCK", "false")
    config.get_settings.cache_clear()
    await default_vision_fn("sys", "prompt")

    kw = goi[-1]
    assert kw["seed"] == config.get_settings().ai_seed
    assert kw["top_p"] == 1.0
    assert kw["temperature"] == 0.0


def test_seed_co_trong_cau_hinh():
    """Đặt được qua biến môi trường để đổi seed khi muốn lấy 'góc nhìn' khác của model."""
    config.get_settings.cache_clear()
    assert isinstance(config.get_settings().ai_seed, int)


async def test_vision_khong_chen_event_loop(monkeypatch):
    """Đường vision cũng phải nhả loop — nó là đường tốn nhất (ingest từng trang).

    Đo bằng đỉnh đồng thời thật (threading.Barrier), không bằng đồng hồ — xem docstring
    `test_ai_call_khong_chen_event_loop` (tests/test_ai_call.py) cho lý do đổi cách đo.
    """
    import asyncio
    import sys
    import threading

    import config
    from experiment.evaluate import vision

    dang_bay = 0
    dinh = 0
    khoa = threading.Lock()
    rao = threading.Barrier(2, timeout=5)   # completion() chạy TRONG thread do to_thread bọc

    class _Cham:
        @staticmethod
        def completion(**kw):
            nonlocal dang_bay, dinh
            with khoa:
                dang_bay += 1
                dinh = max(dinh, dang_bay)
            rao.wait()                      # chặn tới khi ĐỦ 2 luồng cùng vào -> chồng lấn thật
            with khoa:
                dang_bay -= 1
            return {"choices": [{"message": {"content": '{"text": "x"}'}, "finish_reason": "stop"}]}

    monkeypatch.setitem(sys.modules, "litellm", _Cham)
    monkeypatch.setenv("ABES_AI_MOCK", "false")
    # Phải >= 2: nếu chỉ 1, CHÍNH cổng song song sẽ tuần tự hoá hai call -> barrier timeout vì lý
    # do sai (cổng hẹp), không phải vì event loop bị chẹn.
    monkeypatch.setenv("ABES_AI_SONG_SONG", "4")
    config.get_settings.cache_clear()

    await asyncio.gather(vision.default_vision_fn("s", "p"), vision.default_vision_fn("s", "p2"))
    assert dinh == 2, (
        f"đỉnh đồng thời = {dinh} — vẫn đang tuần tự, call LLM đang chẹn event loop"
    )
