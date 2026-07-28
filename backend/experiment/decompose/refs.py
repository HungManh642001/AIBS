"""Trích mã điều khoản (A-CDNT/A-BDL/Mục N) từ text tiêu chí — để neo vào query truy hồi.

Giá trị trong A-HSMT đánh khóa theo mã điều khoản (A-BDL: 'A-CDNT 18.2 | ...'); nhồi mã vào
query giúp BM25 khớp đúng dòng. Lấy cả mã đầy đủ ('18.2') lẫn mã lớn ('18') vì giá trị có thể
nằm ở điều khoản con lân cận (vd tiêu chí trỏ 18.3 nhưng giá trị ở 18.2).
"""
from __future__ import annotations

import re
import unicodedata

_RE_A = re.compile(r"(?:A-?CDNT|A-?BDL|Mục)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_RE_B = re.compile(r"(\d+(?:\.\d+)?)\s*A-?CDNT", re.IGNORECASE)
_RE_FORM = re.compile(r"\bmau\s*(?:so\s*)?(\d+[a-z]?(?:\.\d+)*)\b")  # chạy trên text đã _norm


def _norm(s: str) -> str:
    s = (s or "").lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


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


def extract_form_refs(text: str) -> list[str]:
    """-> mã mẫu ('01', '04a') từ 'Mẫu số 01'/'mẫu 04A' — định tuyến need vào chunk Biểu mẫu."""
    from experiment.index.schema import norm_form_id
    out: list[str] = []
    for m in _RE_FORM.finditer(_norm(text)):
        v = norm_form_id(m.group(1))
        if v not in out:
            out.append(v)
    return out