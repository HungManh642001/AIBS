"""Cache kết quả gọi LLM cho bước phân rã — theo FILE, không đụng DB.

Vì sao cần: chạy lại decompose cho cùng một gói (sửa prompt của một bước rồi soi lại) hiện phải
trả tiền lại cho MỌI bước, kể cả những bước không đổi gì (ANCHORS, SUMMARY, LIST). Với ~40 call
x ~22s thì mỗi vòng lặp thử nghiệm mất vài phút chỉ để dựng lại thứ đã có.

Vì sao theo FILE chứ không theo DB như `services/ai_cache.py`: lõi `experiment/` cố ý KHÔNG biết
DB (xem docstring ai_cache) và chạy được độc lập bằng CLI. Cache nằm trong workdir của gói
(`storage/{id}/rubric_work/llm_cache.json`) nên xoá gói là mất theo, và xoá tay cũng dễ.

KHÓA gồm cả tên model + max_tokens + nguyên văn system/prompt: đổi bất kỳ prompt nào là tự động
trượt cache, không có chuyện dùng lại kết quả của prompt cũ.

CHỈ cache lượt THÀNH CÔNG. Lỗi proxy mà cache lại thì lần chạy sau vẫn hỏng dù proxy đã sống —
đúng tinh thần no-silent-mock.

Cache còn làm kết quả DỄ TÁI LẬP HƠN: temperature=0 không đủ để tái lập vì vLLM gộp batch động
nên thứ tự cộng số thực đổi theo tải; đọc lại đúng bản đã lưu thì hết dao động đó.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from services.ai_client import AiOutcome

log = logging.getLogger("experiment.decompose")

_TEN_FILE = "llm_cache.json"


def khoa_goi(model: str, system: str, prompt: str, max_tokens: int | None) -> str:
    """Băm toàn bộ đầu vào quyết định output. Đổi 1 ký tự trong prompt -> khóa khác."""
    h = hashlib.sha256()
    for phan in (model, system, prompt, str(max_tokens)):
        h.update(phan.encode("utf-8"))
        h.update(b"\x00")          # ngăn cách, tránh hai chuỗi khác nhau ghép ra cùng một chuỗi
    return h.hexdigest()


class FileCallCache:
    """Cache {khóa: data} trên một file JSON. Nạp 1 lần, ghi lại sau mỗi lần put."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._data: dict[str, Any] = {}
        if self.path.is_file():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:   # file hỏng -> bắt đầu lại, KHÔNG làm gãy run
                log.warning("[llm-cache] không đọc được %s (%s) -> bỏ qua cache", self.path, exc)
                self._data = {}

    def get(self, key: str) -> dict[str, Any] | None:
        v = self._data.get(key)
        return dict(v) if isinstance(v, dict) else None

    def put(self, key: str, data: dict[str, Any]) -> None:
        self._data[key] = dict(data)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:      # ghi hỏng chỉ mất cache, không được làm hỏng run
            log.warning("[llm-cache] không ghi được %s: %s", self.path, exc)

    def __len__(self) -> int:
        return len(self._data)


def cache_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / _TEN_FILE


def boc_cache(llm_fn: Any, cache: FileCallCache, model: str = "") -> Any:
    """Bọc llm_fn: trúng cache -> trả ngay, 0 call; trượt -> gọi thật rồi lưu nếu ok.

    `put` không có await bên trong nên an toàn khi nhiều need chạy song song trên cùng event loop.
    """
    dem = {"trung": 0, "truot": 0}

    async def goi(system: str, prompt: str, validate: Any = None,
                  max_tokens: int | None = None) -> AiOutcome:
        key = khoa_goi(model, system, prompt, max_tokens)
        san = cache.get(key)
        if san is not None:
            dem["trung"] += 1
            return AiOutcome(status="ok", data=san, model=f"{model or 'llm'} (cache)")
        dem["truot"] += 1
        out = await llm_fn(system, prompt, validate=validate, max_tokens=max_tokens)
        if out.status == "ok" and isinstance(out.data, dict):
            cache.put(key, out.data)
        return out

    goi.dem = dem      # type: ignore[attr-defined]  — để run_decompose log tỉ lệ trúng
    return goi
