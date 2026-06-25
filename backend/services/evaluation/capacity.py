"""F04 - Đánh giá Năng Lực Thực Hiện."""
from __future__ import annotations
from typing import Any

from services.evaluation.base import EvalResult, eval_one

_SYS = "Bạn là chuyên gia đánh giá năng lực nhà thầu. Chỉ trả về JSON."


async def evaluate_capacity(
    criteria: list[dict[str, Any]], hsdt_pages: list[dict[str, Any]]
) -> list[EvalResult]:
    content = "\n".join(f"[Trang {p['page']}] {p['text']}" for p in hsdt_pages)
    return [
        await eval_one(_SYS, c, content, mock_key="eval_capacity")
        for c in criteria if c.get("nhom") == "nang_luc"
    ]
