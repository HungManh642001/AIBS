"""F05 - Đánh giá Kỹ Thuật (chấm điểm theo trọng số)."""
from __future__ import annotations
from typing import Any

from services.evaluation.base import EvalResult, eval_one

_SYS = (
    "Bạn là chuyên gia đánh giá kỹ thuật HSDT, chấm điểm 0-100 theo rubric. "
    "Chỉ trả về JSON."
)


async def evaluate_technical(
    criteria: list[dict[str, Any]], hsdt_pages: list[dict[str, Any]]
) -> list[EvalResult]:
    content = "\n".join(f"[Trang {p['page']}] {p['text']}" for p in hsdt_pages)
    return [
        await eval_one(_SYS, c, content, mock_key="eval_technical")
        for c in criteria if c.get("nhom") == "ky_thuat"
    ]
