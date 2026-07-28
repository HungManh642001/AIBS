"""Bóc JSON từ phản hồi LLM (có Chain-of-Thought) và chuẩn hoá page_ref."""
from __future__ import annotations

import json
import re
import logging
from json import JSONDecoder
from typing import Any

log = logging.getLogger("services.json_utils")

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _strip_trailing_commas(s: str) -> str:
    return _TRAILING_COMMA.sub(r"\1", s)


def _count_braces(s: str) -> int:
    """Đếm số lượng { chưa có } tương ứng."""
    in_str = False
    esc = False
    opened = 0
    for ch in s:
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
            opened += 1
        elif ch == "}":
            opened -= 1
    return max(0, opened)


def _fallback_raw_decode(text: str, start: int) -> dict[str, Any] | None:
    """Fallback: thử raw_decode từ start trước, sau đó mới scan vị trí khác."""
    decoder = JSONDecoder()
    # Ưu tiên parse từ vị trí ngoặc mở ngoài cùng (start)
    try:
        obj, _ = decoder.raw_decode(text, start)
        return obj
    except json.JSONDecodeError:
        pass
    # Nếu thất bại, thử các vị trí khác (inner brace)
    for i in range(start + 1, len(text)):
        if text[i] == "{":
            try:
                obj, _ = decoder.raw_decode(text, i)
                return obj
            except json.JSONDecodeError:
                continue
    return None
    

def _fallback_auto_close(text: str, start: int) -> dict[str, Any] | None:
    """Model bị cutoff → tự đóng string (nếu cần) + ngoặc }."""
    candidate = text[start:]
    
    # Detect state at end of string
    depth = 0
    in_str = False
    esc = False
    for ch in candidate:
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
    
    # Đóng string chưa đóng
    if in_str:
        candidate += '"'
    
    # Đóng ngoặc chưa đóng
    closing_needed = max(0, depth)
    if closing_needed > 0:
        candidate += "}" * closing_needed
    
    candidate = _strip_trailing_commas(candidate)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def extract_json(raw: str) -> dict[str, Any]:
    """Bóc object JSON ngoài cùng. Ưu tiên khối ```json fence; fallback → ném ValueError."""
    if not raw or not raw.strip():
        raise ValueError("Phản hồi AI rỗng")
    text = raw.strip()
    m = _FENCE.search(text)
    if m:
        text = m.group(1).strip()

    start = text.find("{")
    if start == -1:
        raise ValueError("Không tìm thấy JSON object trong phản hồi")

    # Tầng 1: đếm depth (nhanh, xử lý 95% trường hợp)
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
    if end != -1:
        candidate = _strip_trailing_commas(text[start:end])
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            log.warning("extract_json: tầng 1 depth OK nhưng json.loads lỗi: %s", e)

    # Tầng 2: raw_decode từ start (ngoặc ngoài cùng) — không scan inner brace
    try:
        obj, _ = JSONDecoder().raw_decode(text, start)
        log.info("extract_json: tầng 2 raw_decode thành công")
        return obj
    except json.JSONDecodeError:
        pass

    # Tầng 3: tự đóng ngoặc (model cutoff giữa chừng)
    result = _fallback_auto_close(text, start)
    if result is not None:
        log.warning("extract_json: tầng 3 auto-close thành công (model cutoff)")
        return result

    # Tầng 4: raw_decode scan inner brace (last resort)
    result = _fallback_raw_decode(text, start)
    if result is not None:
        log.warning("extract_json: tầng 4 inner brace raw_decode thành công (mất phần ngoài)")
        return result

    preview = raw[-200:].replace("\n", "\\n")
    raise ValueError(f"JSON object không cân bằng ngoặc (preview cuối: ...{preview})")


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
