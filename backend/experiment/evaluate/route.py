"""Tầng B — route nội dung kiểm tra sang trang HSDT có loại hồ sơ khớp hsdt_kiem_tra."""
from __future__ import annotations

import unicodedata

from services import artifact_catalog

from experiment.evaluate.schema import HoSoNhanDuoc, PageRecord, VendorContext


def _norm(s: str) -> str:
    s = (s or "").lower().strip().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def route_pages(pages: list[PageRecord], hsdt_kiem_tra: str) -> list[PageRecord]:
    key = _norm(hsdt_kiem_tra)
    return [p for p in pages if _norm(p.loai_ho_so) == key] if key else []


def pages_by_type(pages: list[PageRecord]) -> dict[str, list[PageRecord]]:
    """Nhóm trang theo loại hồ sơ chuẩn hoá — luật liên-tài-liệu lấy nhiều loại một lúc."""
    out: dict[str, list[PageRecord]] = {}
    for p in pages:
        key = _norm(p.loai_ho_so)
        if key:
            out.setdefault(key, []).append(p)
    return out


def find_vendor_pages(pages: list[PageRecord], ctx: VendorContext) -> list[PageRecord]:
    """TRANG chứa nhà thầu đang chấm — match _norm substring theo tên/MST/aliases.

    Lọc ở mức TRANG: một trang bảng chứa nhiều nhà thầu vẫn được giữ NGUYÊN (kèm nhà thầu khác).
    Việc chọn đúng DÒNG do prompt đảm nhiệm — không lọc theo dòng vì OCR hay tách tên và giá thành
    2 dòng, lọc dòng sẽ âm thầm vứt mất giá.
    """
    keys = [k for k in (_norm(ctx.ten), (ctx.ma_so_thue or "").strip(),
                        *(_norm(a) for a in ctx.aliases)) if k]
    return [p for p in pages if any(k in _norm(p.text) for k in keys)]


def loc_dung_chung(pages: list[PageRecord], loai: str,
                   vendor_ctx: VendorContext | None) -> list[PageRecord]:
    """BẤT BIẾN: KHÔNG BAO GIỜ để dữ liệu nhà thầu KHÁC lọt vào prompt.

    Tài liệu dùng chung (webform...) chứa dữ liệu mọi nhà thầu -> chỉ giữ trang của nhà thầu đang
    chấm. Không có ngữ cảnh nhà thầu -> trả [] (thà thiếu căn cứ còn hơn chấm nhầm dòng người khác).
    Hồ sơ riêng của nhà thầu -> giữ nguyên.
    """
    if not artifact_catalog.la_dung_chung(_norm(loai)):
        return pages
    return find_vendor_pages(pages, vendor_ctx) if vendor_ctx is not None else []


def inventory_pages(pages: list[PageRecord]) -> list[HoSoNhanDuoc]:
    """Danh mục hồ sơ HSDT đã nhận — đầu báo cáo + tra tên file cho số trang bằng chứng."""
    out: dict[str, HoSoNhanDuoc] = {}
    for p in pages:
        key = _norm(p.loai_ho_so)
        if not key:
            continue
        hs = out.setdefault(key, HoSoNhanDuoc(loai_ho_so=key))
        if p.file and p.file not in hs.files:
            hs.files.append(p.file)
        hs.n_trang += 1
    return list(out.values())


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
