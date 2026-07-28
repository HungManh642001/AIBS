"""Định vị mục Tiêu chuẩn đánh giá (TCĐG) + Bảng dữ liệu đấu thầu (BDS) trong HSMT lớn.

Trả dải trang (từ heading bắt đầu đến heading mục lớn kế tiếp), không lấy lẻ trang,
và KHÔNG fallback nạp toàn bộ tài liệu khi không định vị được.
"""
from __future__ import annotations

import unicodedata

# Heading nhận diện (đã bỏ dấu, lowercase) — so khớp trên text đã chuẩn hoá.
_TCDG_KW = ["tieu chuan danh gia"]
_BDS_KW = ["bang du lieu dau thau", "bang du lieu", "bds"]
# Heading "mục lớn" để biết một dải kết thúc ở đâu.
_SECTION_KW = _TCDG_KW + _BDS_KW + ["chuong ", "phan ", "muc "]


def _norm(text: str) -> str:
    """Lowercase + bỏ dấu tiếng Việt để chống lỗi OCR/biến thể.

    NFD tách hầu hết nguyên âm có dấu; riêng đ/Đ không phân rã nên thay thủ công.
    """
    lowered = text.lower().replace("đ", "d")
    nfkd = unicodedata.normalize("NFD", lowered)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def _starts(norm_text: str, keywords: list[str]) -> bool:
    return any(k in norm_text for k in keywords)


def _range_from(pages: list[dict], norms: list[str], start_kw: list[str]) -> dict:
    """Tìm trang bắt đầu (chứa heading start_kw); lấy đến trước heading mục lớn kế tiếp."""
    start = next((i for i, n in enumerate(norms) if _starts(n, start_kw)), None)
    if start is None:
        return {"located": False, "pages": []}
    end = len(pages)
    for j in range(start + 1, len(pages)):
        # Kết thúc khi gặp heading mục lớn KHÁC (không thuộc cùng nhóm start_kw).
        if _starts(norms[j], _SECTION_KW) and not _starts(norms[j], start_kw):
            end = j
            break
    return {"located": True, "pages": pages[start:end]}


def locate_hsmt_sections(hsmt_pages: list[dict]) -> dict:
    """Định vị TCĐG và BDS thành dải trang.

    Returns:
        {"tcdg": {"located": bool, "pages": [...]},
         "bds":  {"located": bool, "pages": [...]}}
    """
    norms = [_norm(p.get("text", "")) for p in hsmt_pages]
    return {
        "tcdg": _range_from(hsmt_pages, norms, _TCDG_KW),
        "bds": _range_from(hsmt_pages, norms, _BDS_KW),
    }
