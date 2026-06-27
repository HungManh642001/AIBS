"""Lọc nhiễu cấu trúc: bỏ cụm mục lục, giữ chuỗi Chương đơn điệu."""
from __future__ import annotations

from collections import defaultdict

from .schema import Heading

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman_to_int(s: str) -> int:
    total, prev = 0, 0
    for ch in reversed(s.upper()):
        v = _ROMAN.get(ch, 0)
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


def drop_toc_clusters(headings: list[Heading], min_cluster: int = 4) -> list[Heading]:
    """Trang nào có >= min_cluster heading cấp <=1 (Phần/Chương) là mục lục/overview -> bỏ cả trang."""
    by_page: dict[int, list[Heading]] = defaultdict(list)
    for h in headings:
        by_page[h.page].append(h)
    toc_pages = {p for p, hs in by_page.items()
                 if sum(1 for h in hs if h.level <= 1) >= min_cluster}
    return [h for h in headings if h.page not in toc_pages]


def _chapter_value(number: str) -> int:
    return roman_to_int(number) if number.isalpha() else int(number)


def keep_monotonic_chapters(headings: list[Heading]) -> list[Heading]:
    """Giữ Chương chỉ khi số tăng đúng +1 theo thứ tự đọc; loại Chương nhảy cóc (ref sót)."""
    out: list[Heading] = []
    last = 0
    for h in headings:
        if h.kind == "chuong":
            val = _chapter_value(h.number)
            if val == last + 1:
                last = val
                out.append(h)
            # else: bỏ — heading Chương lệch chuỗi
        else:
            out.append(h)
    return out
