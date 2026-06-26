"""Định vị mục Tiêu chuẩn đánh giá (TCĐG) + Bảng dữ liệu đấu thầu (BDS) trong HSMT lớn."""
from __future__ import annotations

_TCDG_KW = ["tiêu chuẩn đánh giá", "tieu chuan danh gia"]
_BDS_KW = ["bảng dữ liệu đấu thầu", "bang du lieu dau thau", "bảng dữ liệu"]


def _pick(pages: list[dict], keywords: list[str]) -> list[dict]:
    """Lọc pages chứa bất kỳ keyword nào (case-insensitive)."""
    out = [p for p in pages if any(k in p["text"].lower() for k in keywords)]
    return out


def locate_hsmt_sections(hsmt_pages: list[dict]) -> dict:
    """Định vị TCĐG và BDS sections trong danh sách pages.

    Args:
        hsmt_pages: Danh sách pages với shape {"page": int, "text": str}

    Returns:
        Dict với keys "tcdg" và "bds", mỗi value là list of pages.
        Fallback: nếu không tìm được trang nào cho một section,
        return toàn bộ hsmt_pages để extraction vẫn chạy.
    """
    tcdg = _pick(hsmt_pages, _TCDG_KW)
    bds = _pick(hsmt_pages, _BDS_KW)

    # Fallback: không định vị được -> dùng toàn bộ trang để extraction vẫn chạy
    if not tcdg:
        tcdg = hsmt_pages
    if not bds:
        bds = hsmt_pages

    return {"tcdg": tcdg, "bds": bds}
