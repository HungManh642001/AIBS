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
