from config import Settings


def test_ai_tuning_defaults():
    s = Settings()
    assert s.ai_temperature == 0.0
    assert s.ai_max_tokens == 4096
