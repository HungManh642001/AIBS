"""Phân loại dòng heading bằng cờ bold + regex siết (font-size vô dụng ở HSMT này)."""
from __future__ import annotations

import re
import unicodedata

from .schema import Line, Heading, LEVEL_PHAN, LEVEL_CHUONG, LEVEL_MUC, LEVEL_DIEU


def _norm(text: str) -> str:
    lowered = text.lower().replace("đ", "d")
    nfkd = unicodedata.normalize("NFD", lowered)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


# Số/La Mã PHẢI theo sau bởi [.:-–] để không nuốt chữ thường ("phan viec", "chuong v chi...").
_PATTERNS = [
    ("phan", LEVEL_PHAN, re.compile(r"^phan\s+(\d{1,2}|[ivxlc]+)\s*[\.\:\-–]")),
    ("chuong", LEVEL_CHUONG, re.compile(r"^chuong\s+([ivxlc]+|\d{1,2})\s*[\.\:\-–]")),
    ("muc", LEVEL_MUC, re.compile(r"^muc\s+(\d{1,2})\s*[\.\:]")),
    ("dieu", LEVEL_DIEU, re.compile(r"^dieu\s+(\d{1,2})\s*[\.\:]")),
]


def classify_heading(line: Line) -> Heading | None:
    if not line.bold:
        return None
    norm = _norm(line.text.strip())
    for kind, level, rx in _PATTERNS:
        m = rx.match(norm)
        if m:
            return Heading(kind=kind, level=level, number=m.group(1).upper(),
                           title=line.text.strip(), page=line.page, y0=line.y0)
    return None
