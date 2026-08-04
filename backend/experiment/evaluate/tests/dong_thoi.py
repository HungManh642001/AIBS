"""Vision giả ĐẾM số call đang bay — dùng để chứng minh gather thật sự chạy chồng nhau.

Không có phép đo này thì một `gather` vẫn có thể tuần tự (vì bên dưới còn chỗ chẹn loop) mà test
kết quả vẫn xanh — đúng cái bệnh plan này chữa.
"""
from __future__ import annotations

import asyncio
from typing import Any

from services.ai_client import AiOutcome


class VisionDemDongThoi:
    """vision_fn giả: mỗi call nhường loop vài nhịp rồi trả `data`. Ghi lại đỉnh đồng thời."""

    def __init__(self, data: dict[str, Any] | None = None, nhip: int = 3):
        self._data = data if data is not None else {"text": "x"}
        self._nhip = nhip
        self.dang_bay = 0
        self.dinh = 0
        self.so_call = 0

    async def __call__(self, system: str, prompt: str, images: list[bytes] = (),
                       validate: Any = None, **kw: Any) -> AiOutcome:
        self.dang_bay += 1
        self.dinh = max(self.dinh, self.dang_bay)
        self.so_call += 1
        try:
            for _ in range(self._nhip):
                await asyncio.sleep(0)     # nhường loop: call khác có cơ hội vào
            data = dict(self._data)
            return AiOutcome("ok", validate(data) if validate else data, "fake")
        finally:
            self.dang_bay -= 1
