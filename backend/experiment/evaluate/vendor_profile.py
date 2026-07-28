from __future__ import annotations

from experiment.logger_config import setup_logger

from experiment.evaluate.prompts import SYS_VENDOR_FORM, vendor_form_prompt
from experiment.evaluate.route import _norm, pages_by_type, pages_text
from experiment.evaluate.schema import (
    HINH_THUC_DOC_LAP, HINH_THUC_KHONG_RO, HINH_THUC_LIEN_DANH,
    NGUON_DON_DU_THAU, NGUON_HO_SO, NGUON_KHAI_BAO, NGUON_KHONG_DU_CAN_CU,
    PageRecord, VendorContext, VendorProfile, validate_vendor_form
)
from experiment.evaluate.vision import VisionFn

log = setup_logger("EVALUATE", "evaluate.log")

_MA_LIEN_DANH = "thoa_thuan_lien_danh"
_MA_DON = "don_du_thau"
_DO_TIN_TOI_THIEU = 0.7
_DON_CAP = 8000
_MAX_TOKEN = 1024


def canon_hinh_thuc(raw: str) -> str:
    """'doc_lap'/'Độc Lập'/'lien-danh' -> hằng chuẩn; không nhận diện -> '' (KHÔNG đoán)."""
    key = _norm(raw).replace("_", " ").replace("-", " ")
    key = " ".join(key.split())
    if key in {"doc lap", "doclap"}:
        return HINH_THUC_DOC_LAP
    if key in {"lien danh", "liendanh"}:
        return HINH_THUC_LIEN_DANH
    return HINH_THUC_KHONG_RO


async def detect_vendor_profile(pages: list[PageRecord], vision_fn: VisionFn, *, 
                                vendor: VendorContext | None = None) -> VendorProfile:
    by_type = pages_by_type(pages)
    lien_danh_pages = by_type.get(_MA_LIEN_DANH) or []
    co_ttld = bool(lien_danh_pages)
    khai_bao = canon_hinh_thuc(vendor.hinh_thuc) if vendor is not None else HINH_THUC_KHONG_RO

    if khai_bao:
        ho_so_noi = HINH_THUC_LIEN_DANH if co_ttld else HINH_THUC_DOC_LAP
        if khai_bao == ho_so_noi:
            return VendorProfile(hinh_thuc=khai_bao, nguon=NGUON_KHAI_BAO, do_tin=1.0)
        chi_tiet = (f"HSDT CÓ hồ sơ '{_MA_LIEN_DANH}' ({lien_danh_pages[0].file})" if co_ttld
                    else f"HSDT KHÔNG có hồ sơ '{_MA_LIEN_DANH}'")
        return VendorProfile(
            hinh_thuc=HINH_THUC_KHONG_RO, nguon=NGUON_KHONG_DU_CAN_CU, mau_thuan=True,
            ghi_chu=(f"khai báo hình thức '{khai_bao}' nhưng {chi_tiet} - hình thức đặt KHÔNG RÕ, "
                     f"mọi nội dung liên danh VẪN được chấm đầy đủ; cần chuyên gia xác minh")
        )
    
    if co_ttld:
        return VendorProfile(
            hinh_thuc=HINH_THUC_LIEN_DANH, nguon=NGUON_HO_SO, do_tin=1.0,
            bang_chung=f"HSDT có hồ sơ '{_MA_LIEN_DANH}' ({lien_danh_pages[0].file})",
            trang=[p.trang for p in lien_danh_pages]
        )
    
    don_pages = by_type.get(_MA_DON) or []
    if don_pages:
        return await _detect_tu_don(don_pages, vision_fn, vendor)
    
    return VendorProfile()


async def _detect_tu_don(don_pages: list[PageRecord], vision_fn: VisionFn,
                         vendor: VendorContext | None) -> VendorProfile:
    """TẮT: người dùng khai báo hình thức (độc lập/liên danh) khi tạo nhà thầu, nên không
    cần LLM đọc đơn dự thầu để suy ra. Trả hồ sơ RỖNG = "không rõ" -> KHÔNG bao giờ gate,
    mọi nội dung liên danh vẫn được chấm đủ."""
    return VendorProfile()