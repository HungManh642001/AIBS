"""Bóc JSON từ phản hồi LLM (có Chain-of-Thought) và chuẩn hoá page_ref."""
from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _strip_trailing_commas(s: str) -> str:
    return _TRAILING_COMMA.sub(r"\1", s)


def extract_json(raw: str) -> dict[str, Any]:
    """Bóc object JSON ngoài cùng. Ưu tiên khối ```json fence; ném ValueError nếu thất bại."""
    if not raw or not raw.strip():
        raise ValueError("Phản hồi AI rỗng")
    text = raw.strip()
    m = _FENCE.search(text)
    if m:
        text = m.group(1).strip()

    start = text.find("{")
    if start == -1:
        raise ValueError("Không tìm thấy JSON object trong phản hồi")

    depth = 0
    in_str = False
    esc = False
    end = -1
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        raise ValueError("JSON object không cân bằng ngoặc")

    candidate = _strip_trailing_commas(text[start:end])
    return json.loads(candidate)


def clamp_page_refs(refs: Any, max_page: int = 0) -> list[int]:
    """Giữ lại các số trang hợp lệ (int >= 1, <= max_page nếu max_page > 0). Bỏ bool/non-int."""
    out: list[int] = []
    for r in refs or []:
        if isinstance(r, bool) or not isinstance(r, int):
            continue
        if r < 1:
            continue
        if max_page and r > max_page:
            continue
        out.append(r)
    return out
