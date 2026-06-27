"""Nhận diện Mục dạng 'con trỏ' (tham chiếu sang Phần/Chương/Mục khác). CHƯA lần theo."""
from __future__ import annotations

import re

from experiment.chunking.headings import _norm

# "theo ... (tại) (phan|chuong|muc) <số/La Mã>"  — chạy trên text đã bỏ dấu.
_REF_RE = re.compile(r"theo\b.*?\b(phan|chuong|muc)\s+(\d{1,2}|[ivxlc]+)\b")
_MAX_REF_LEN = 300  # con trỏ là Mục ngắn; text dài coi như nội dung inline


def detect_reference(text: str) -> tuple[bool, dict | None]:
    """Trả (is_reference, ref_target). True khi Mục ngắn và chứa cụm dẫn 'theo … Phần/Chương/Mục X'."""
    stripped = (text or "").strip()
    if not stripped or len(stripped) > _MAX_REF_LEN:
        return (False, None)
    m = _REF_RE.search(_norm(stripped))
    if not m:
        return (False, None)
    return (True, {"kind": m.group(1), "number": m.group(2).upper()})
