"""Helper kiểm tra tất định (Python) cho các check_type có số/ngày — không phụ thuộc AI."""
from __future__ import annotations

import re
from typing import Any


def _max_number(text: str) -> int | None:
    """Trích số lớn nhất (bỏ '.'/',' ngăn cách hàng nghìn)."""
    candidates = re.findall(r"\d[\d.,]*", text)
    nums: list[int] = []
    for c in candidates:
        digits = c.replace(".", "").replace(",", "")
        if digits.isdigit():
            nums.append(int(digits))
    return max(nums) if nums else None


def _days(text: str) -> int | None:
    """Trích số ngày từ pattern '<N> ngày'."""
    m = re.search(r"(\d+)\s*ngày", text.lower())
    return int(m.group(1)) if m else None


def run_deterministic_check(
    check_type: str, content: str, thong_so: dict[str, Any]
) -> dict[str, Any] | None:
    """
    Kiểm tra tất định (Python) cho các check_type: presence, value_threshold, date_validity.

    Args:
        check_type: loại kiểm tra ("presence", "value_threshold", "date_validity", hoặc khác)
        content: nội dung cần kiểm tra
        thong_so: dict chứa thông số ("gia_tri_so", "so_ngay", v.v.)

    Returns:
        dict với {"result": "PASS"|"FAIL", "evidence": str} hoặc None nếu không áp dụng được.
    """
    if check_type == "presence":
        ok = bool(content.strip())
        return {
            "result": "PASS" if ok else "FAIL",
            "evidence": "Có nội dung hồ sơ" if ok else "Hồ sơ rỗng",
        }

    if check_type == "value_threshold":
        nguong = thong_so.get("gia_tri_so")
        val = _max_number(content)
        if nguong is None or val is None:
            return None
        ok = val >= int(nguong)
        return {
            "result": "PASS" if ok else "FAIL",
            "evidence": f"Giá trị trích được {val:,} so với ngưỡng {int(nguong):,}",
        }

    if check_type == "date_validity":
        nguong = thong_so.get("so_ngay")
        d = _days(content)
        if nguong is None or d is None:
            return None
        ok = d >= int(nguong)
        return {
            "result": "PASS" if ok else "FAIL",
            "evidence": f"Hiệu lực {d} ngày so với yêu cầu {int(nguong)} ngày",
        }

    return None
