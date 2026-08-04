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
    """Đường vision cũng phải nhả loop — nó là đường tốn nhất (ingest từng trang)."""
    import asyncio
    import sys
    import time

    import config
    from experiment.evaluate import vision

    class _Cham:
        @staticmethod
        def completion(**kw):
            time.sleep(0.20)
            return {"choices": [{"message": {"content": '{"text": "x"}'}, "finish_reason": "stop"}]}

    monkeypatch.setitem(sys.modules, "litellm", _Cham)
    monkeypatch.setenv("ABES_AI_MOCK", "false")
    monkeypatch.setenv("ABES_AI_SONG_SONG", "4")
    config.get_settings.cache_clear()

    t0 = time.perf_counter()
    await asyncio.gather(vision.default_vision_fn("s", "p"), vision.default_vision_fn("s", "p2"))
    trong = time.perf_counter() - t0
    assert trong < 0.35, f"hai call vision mất {trong:.2f}s — vẫn đang tuần tự"
