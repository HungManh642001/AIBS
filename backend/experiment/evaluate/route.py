"""Tầng B — route nội dung kiểm tra sang trang HSDT có loại hồ sơ khớp hsdt_kiem_tra."""
from __future__ import annotations

import unicodedata

from experiment.evaluate.schema import PageRecord


def _norm(s: str) -> str:
    s = (s or "").lower().strip().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def route_pages(pages: list[PageRecord], hsdt_kiem_tra: str) -> list[PageRecord]:
    key = _norm(hsdt_kiem_tra)
    return [p for p in pages if _norm(p.loai_ho_so) == key] if key else []


def _flags(p: PageRecord) -> str:
    """Hiện cờ thị giác trong text để eval biết có chữ ký/đóng dấu (bù cho việc không đính ảnh)."""
    fs = []
    if p.co_chu_ky:
        fs.append("có chữ ký")
    if p.co_dau:
        fs.append("có đóng dấu")
    return f" ({'; '.join(fs)})" if fs else ""


def pages_text(pages: list[PageRecord]) -> str:
    return "\n".join(f"[Trang {p.trang}]{_flags(p)} {p.text}" for p in pages)
