"""Trích xuất tiêu chí từ HSMT và mapping nội dung HSDT vào tiêu chí."""
from __future__ import annotations
from typing import Any

from services.ai_client import ai_json

_SYS_EXTRACT = (
    "Bạn là chuyên gia đấu thầu theo Luật Đấu thầu Việt Nam. "
    "Trích xuất toàn bộ tiêu chí đánh giá trong HSMT và phân vào 4 nhóm: "
    "hop_le, nang_luc, ky_thuat, tai_chinh. Chỉ trả về JSON."
)
_SYS_MAP = (
    "Bạn là chuyên gia đấu thầu. Với mỗi tiêu chí, tìm nội dung tương ứng "
    "trong HSDT kèm số trang. Chỉ trả về JSON."
)


def _join(pages: list[dict[str, Any]], limit: int = 12000) -> str:
    text = "\n".join(f"[Trang {p['page']}]\n{p['text']}" for p in pages)
    return text[:limit]


async def extract_criteria(hsmt_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prompt = (
        "HSMT:\n" + _join(hsmt_pages) +
        '\n\nTrả về JSON: {"criteria":[{"nhom","ten","yeu_cau","kieu","trong_so"}]}'
    )
    data = await ai_json(_SYS_EXTRACT, prompt, mock_key="extract_criteria")
    return data.get("criteria", [])


async def map_hsdt(
    criteria: list[dict[str, Any]], hsdt_pages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    names = ", ".join(c.get("ten", "") for c in criteria)
    prompt = (
        f"Tiêu chí: {names}\n\nHSDT:\n" + _join(hsdt_pages) +
        '\n\nTrả về JSON: {"mappings":[{"criteria_ten","page_ref","content"}]}'
    )
    data = await ai_json(_SYS_MAP, prompt, mock_key="map_hsdt")
    return data.get("mappings", [])
