"""Lưu trữ file trên local filesystem (demo). Production -> MinIO."""
import re
from pathlib import Path

from config import get_settings

STORAGE_DIR: Path = get_settings().storage_dir


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def save_upload(package_id: int, filename: str, content: bytes, subdir: str) -> str:
    rel_dir = Path(str(package_id)) / subdir
    target_dir = STORAGE_DIR / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    rel = rel_dir / _safe(filename)
    (STORAGE_DIR / rel).write_bytes(content)
    return str(rel).replace("\\", "/")


def abs_path(rel: str) -> Path:
    return STORAGE_DIR / rel


def read_bytes(rel: str) -> bytes:
    return (STORAGE_DIR / rel).read_bytes()
