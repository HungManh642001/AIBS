"""Cache kết quả CHẤM — chấm lại cùng hồ sơ + cùng tiêu chí phải ra y hệt, không hỏi lại model.

VÌ SAO: mỗi lần chấm một nhà thầu là hàng chục call (dò hình thức, từng nội dung kiểm tra, các
luật thường trực...). Model không tái lập tuyệt đối kể cả temperature=0 + seed (vLLM gộp batch
động), nên chỉ cần vài call lệch là bảng kết quả khác hẳn lần trước — chuyên gia mất niềm tin và
không đối chứng được với biên bản đã in.

CÁCH: mọi call LLM lúc chấm đều đi qua MỘT cửa duy nhất — tham số `vision_fn` — nên bọc một lớp ở
đây là phủ hết, không phải sửa dòng nào trong các luật. Khóa = hash toàn bộ đầu vào (system +
prompt + model + tham số sinh); prompt đã chứa cả text hồ sơ lẫn tiêu chí nên:
- đổi tiêu chí / sửa hồ sơ -> prompt đổi -> khóa đổi -> chấm mới;
- không đổi gì            -> đọc lại kết quả cũ, 0 call.

Hai điều KHÔNG cache (giống cache OCR):
- call kèm ẢNH: đó là của ingest, đã có cache riêng ở tầng trên;
- kết quả LỖI: proxy hỏng một lần mà cache lại thì lỗi tạm thời hóa vĩnh viễn.

Muốn model làm lại từ đầu thì xóa cache (endpoint DELETE .../cache) — chấm lại KHÔNG tự ý hỏi lại.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Protocol

from config import get_settings
from services.ai_client import AiOutcome

log = logging.getLogger("experiment.evaluate")

MODEL_CACHE = "cache"    # AiOutcome.model khi dữ liệu lấy từ cache (audit: không phải call mới)


class CallCache(Protocol):
    """Kho kết quả call theo khóa. Triển khai thật: services/ai_cache.py (DB)."""

    def get(self, key: str) -> dict[str, Any] | None: ...

    def put(self, key: str, data: dict[str, Any]) -> None: ...


def khoa_call(system: str, prompt: str, max_tokens: int | None) -> str:
    """Khóa = toàn bộ thứ quyết định câu trả lời: prompt + model + tham số sinh."""
    s = get_settings()
    van = "\n".join([system, prompt, s.ai_model, str(s.ai_temperature), str(s.ai_seed),
                     str(max_tokens or s.ai_max_tokens)])
    return hashlib.sha256(van.encode("utf-8")).hexdigest()[:48]


class CachedVision:
    """Bọc một vision_fn: trả kết quả đã lưu nếu đầu vào không đổi."""

    def __init__(self, inner: Any, store: CallCache):
        self._inner = inner
        self._store = store

    async def __call__(self, system: str, prompt: str, images: list[bytes] = (),
                       validate: Any = None, max_tokens: int | None = None,
                       **kw: Any) -> AiOutcome:
        if images:      # call của ingest — cache ở tầng trên, không cache lại
            return await self._inner(system, prompt, images=images, validate=validate,
                                     max_tokens=max_tokens, **kw)

        key = khoa_call(system, prompt, max_tokens)
        luu = self._store.get(key)
        if luu is not None:
            # Vẫn validate: schema đổi thì không nuốt dữ liệu cũ sai kiểu.
            data = validate(luu) if validate is not None else luu
            return AiOutcome("ok", data, MODEL_CACHE)

        out = await self._inner(system, prompt, images=images, validate=validate,
                                max_tokens=max_tokens, **kw)
        if out.status == "ok" and out.data is not None:
            self._store.put(key, out.data)
        return out
