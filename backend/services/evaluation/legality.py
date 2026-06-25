"""F03 - Đánh giá Tính Hợp Lệ."""
from __future__ import annotations
from typing import Any

from services.evaluation.base import EvalResult, eval_one

_SYS = (
    "Bạn là chuyên gia đánh giá tính hợp lệ HSDT theo Luật Đấu thầu Việt Nam. "
    "Chỉ trả về JSON."
)


def _content(pages: list[dict[str, Any]]) -> str:
    return "\n".join(f"[Trang {p['page']}] {p['text']}" for p in pages)


async def evaluate_legality(
    criteria: list[dict[str, Any]], hsdt_pages: list[dict[str, Any]]
) -> list[EvalResult]:
    content = _content(hsdt_pages)
    out: list[EvalResult] = []
    for c in criteria:
        if c.get("nhom") == "hop_le":
            out.append(await eval_one(_SYS, c, content, mock_key="eval_legality"))
    return out
