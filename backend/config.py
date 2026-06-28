"""Cấu hình ứng dụng, đọc từ biến môi trường (có giá trị mặc định cho demo)."""
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ABES_", env_file=".env")

    storage_dir: Path = BASE_DIR / "storage"
    db_url: str = f"sqlite:///{BASE_DIR / 'abes_demo.db'}"
    ai_base_url: str = "http://localhost:4000/v1"  # LiteLLM Proxy (OpenAI-compatible, kết thúc bằng /v1)
    ai_api_key: str = ""                           # API key của LiteLLM Proxy
    ai_model: str = "qwen3.6-27b"
    ai_embed_model: str = "bge-m3"                  # model embedding qua LiteLLM proxy (bước index)
    ai_mock: bool = False                          # True -> luôn dùng mock
    ai_temperature: float = 0.0                    # 0 -> tái lập kết quả
    ai_max_tokens: int = 4096                       # giới hạn token sinh (đánh giá/sub-check)
    ai_max_tokens_extract: int = 8192              # token cho bước liệt kê tiêu chí (output dài)
    ai_chunk_chars: int = 12000                     # ngân sách ký tự mỗi chunk
    ai_chunk_overlap: int = 800                     # overlap giữa các chunk


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.storage_dir.mkdir(parents=True, exist_ok=True)
    return s
