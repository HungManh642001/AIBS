"""Cấu hình ứng dụng, đọc từ biến môi trường (có giá trị mặc định cho demo)."""
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ABES_", env_file=".env")

    storage_dir: Path = BASE_DIR / "storage"
    db_url: str = f"sqlite:///{BASE_DIR / 'abes_demo.db'}"
    ai_base_url: str = "http://10.10.50.58:30099/v1"   # LiteLLM proxy
    # BÍ MẬT — mặc định RỖNG, đặt ABES_AI_API_KEY trong backend/.env (đã .gitignore).
    # Đừng ghi key thật vào đây: file này vào git, key sẽ nằm vĩnh viễn trong lịch sử.
    ai_api_key: str = ""
    ollama_url: str = "http://192.168.24.237:11434"
    ai_embed_model: str = "bge-m3"
    ai_model: str = "qwen3.6-27b"
    ai_mock: bool = False                          # True -> luôn dùng mock
    ai_temperature: float = 0.0
    ai_seed: int = 42
    ai_max_tokens: int = 4096
    ai_max_tokens_extract: int = 8192
    ai_chunk_chars: int = 120000
    ai_chunk_overlap: int = 800

@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.storage_dir.mkdir(parents=True, exist_ok=True)
    return s
