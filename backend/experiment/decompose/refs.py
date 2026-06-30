"""Trích mã điều khoản (E-CDNT/E-BDL/Mục N) từ text tiêu chí — để neo vào query truy hồi.

Giá trị trong E-HSMT đánh khóa theo mã điều khoản (E-BDL: 'E-CDNT 18.2 | ...'); nhồi mã vào
query giúp BM25 khớp đúng dòng. Lấy cả mã đầy đủ ('18.2') lẫn mã lớn ('18') vì giá trị có thể
nằm ở điều khoản con lân cận (vd tiêu chí trỏ 18.3 nhưng giá trị ở 18.2).
"""
from __future__ import annotations

import re

_RE_A = re.compile(r"(?:E-?CDNT|E-?BDL|Mục)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_RE_B = re.compile(r"(\d+(?:\.\d+)?)\s*E-?CDNT", re.IGNORECASE)


def extract_clause_refs(text: str) -> list[str]:
    """-> danh sách mã điều khoản (giữ thứ tự, khử trùng), kèm mã lớn. '' -> []."""
    t = text or ""
    found = _RE_A.findall(t) + _RE_B.findall(t)
    out: list[str] = []
    for r in found:
        cands = [r, r.split(".")[0]] if "." in r else [r]
        for v in cands:
            if v and v not in out:
                out.append(v)
    return out
