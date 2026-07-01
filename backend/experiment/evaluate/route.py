"""Tầng B — route nội dung kiểm tra sang trang HSDT có loại hồ sơ khớp hsdt_kiem_tra."""
from __future__ import annotations

import unicodedata

from experiment.evaluate.schema import PageRecord

_VISUAL = ("chu ky", "dau")  # chữ ký / con dấu / đóng dấu


def _norm(s: str) -> str:
    s = (s or "").lower().strip().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def route_pages(pages: list[PageRecord], hsdt_kiem_tra: str) -> list[PageRecord]:
    key = _norm(hsdt_kiem_tra)
    return [p for p in pages if _norm(p.loai_ho_so) == key] if key else []


def pages_text(pages: list[PageRecord]) -> str:
    return "\n".join(f"[Trang {p.trang}] {p.text}" for p in pages)


def has_visual_check(kieu_check: str) -> bool:
    n = _norm(kieu_check)
    return any(v in n for v in _VISUAL)
