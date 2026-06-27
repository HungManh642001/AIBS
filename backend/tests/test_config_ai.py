from config import Settings


def test_ai_tuning_defaults():
    s = Settings()
    assert s.ai_temperature == 0.0
    assert s.ai_max_tokens == 4096
    assert s.ai_max_tokens_extract == 8192
    assert s.ai_chunk_chars == 12000
    assert s.ai_chunk_overlap == 800
