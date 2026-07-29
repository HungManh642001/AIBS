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


_ESCAPE_HOP_LE = set('"\\/bfnrtu')


def va_escape(s: str) -> str:
    """Escape các dấu `\\` KHÔNG mở đầu một escape hợp lệ của JSON — chỉ bên trong chuỗi.

    LLM rất hay nhả LaTeX (`$\\ge$`), phần trăm (`\\%`) hay đường dẫn Windows (`C:\\Users`) vào giữa
    chuỗi. JSON chỉ cho phép \\" \\\\ \\/ \\b \\f \\n \\r \\t \\uXXXX, nên `\\g` làm json.loads ném
    `Invalid \\escape` và cả object bị vứt dù nội dung hoàn toàn đọc được.

    Vá KHÔNG mất dữ liệu: `$\\ge$` trở thành literal `$\ge$` trong chuỗi kết quả.

    CHỈ đụng phần trong chuỗi — ngoài chuỗi mà có `\\` thì đó là hỏng kiểu khác, để tầng sau lo.
    """
    out: list[str] = []
    in_str = False
    i = 0
    while i < len(s):
        ch = s[i]
        if not in_str:
            if ch == '"':
                in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "\\":
            ke = s[i + 1] if i + 1 < len(s) else ""
            if ke in _ESCAPE_HOP_LE:
                out.append(ch)
                out.append(ke)      # nuốt luôn ký tự sau: `\"` không được tính là đóng chuỗi
                i += 2
                continue
            out.append("\\\\")      # dấu \ đứng một mình -> nhân đôi cho hợp lệ
            i += 1
            continue
        if ch == '"':
            in_str = False
        out.append(ch)
        i += 1
    return "".join(out)


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
    ly_do_that = ""   # nguyên nhân THẬT của tầng 1 — giữ để báo đúng bệnh ở cuối
    if end != -1:
        candidate = _strip_trailing_commas(text[start:end])
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            ly_do_that = str(e)
            log.warning("extract_json: tầng 1 depth OK nhưng json.loads lỗi: %s", e)

        # Tầng 1b: ngoặc đã cân bằng mà vẫn lỗi -> thủ phạm thường là escape không hợp lệ
        # (LaTeX/đường dẫn). Vá rồi thử lại TRƯỚC các tầng chữa-ngoặc, vì ngoặc đâu có hỏng.
        va = va_escape(candidate)
        if va != candidate:
            try:
                obj = json.loads(va)
                log.warning("extract_json: tầng 1b vá escape hỏng thành công (%s)", ly_do_that)
                return obj
            except json.JSONDecodeError as e:
                log.warning("extract_json: tầng 1b vá escape vẫn lỗi: %s", e)

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
    # Báo ĐÚNG bệnh: nếu tầng 1 đã đếm được ngoặc cân bằng thì ngoặc KHÔNG phải vấn đề, và ta đã
    # biết lỗi thật từ json.loads. Nói "không cân bằng ngoặc" ở ca đó là đẩy người debug đi sai
    # hướng — chính chỗ này từng làm mất thời gian truy một lỗi escape LaTeX.
    ly_do = ly_do_that if ly_do_that else "không cân bằng ngoặc"
    raise ValueError(f"Không parse được JSON ({ly_do}) (preview cuối: ...{preview})")


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
