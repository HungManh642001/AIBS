"""Xác định HÌNH THỨC DỰ THẦU của nhà thầu (độc lập / liên danh) — hybrid, có căn cứ.

Thứ tự nhánh BẮT BUỘC (mỗi nhánh dừng luôn):
  (a) khai báo + nhất quán với hồ sơ -> khai báo           0 call
  (b) khai báo ≠ hồ sơ               -> "" + mau_thuan     0 call   <- FAIL-SAFE
  (c) có hồ sơ thỏa thuận liên danh  -> liên danh          0 call
  (d) có đơn dự thầu                 -> LLM đọc đơn        1 call
  (e) còn lại                        -> "" không đủ căn cứ 0 call

"" (không rõ) KHÔNG BAO GIỜ gate — nội dung liên danh vẫn được chấm đủ như khi chưa có tính năng
này. Sai một lần ở đây là bỏ sót cả tiêu chí tiên quyết, nên mọi đường mơ hồ/lỗi đều trả "".
"""
from __future__ import annotations

import logging

from experiment.evaluate.prompts import SYS_VENDOR_FORM, vendor_form_prompt
from experiment.evaluate.route import _norm, pages_by_type, pages_text
from experiment.evaluate.schema import (
    HINH_THUC_DOC_LAP, HINH_THUC_KHONG_RO, HINH_THUC_LIEN_DANH,
    NGUON_DON_DU_THAU, NGUON_HO_SO, NGUON_KHAI_BAO, NGUON_KHONG_DU_CAN_CU,
    PageRecord, VendorContext, VendorProfile, validate_vendor_form,
)
from experiment.evaluate.vision import VisionFn

log = logging.getLogger("experiment.evaluate")

_MA_LIEN_DANH = "thoa_thuan_lien_danh"
_MA_DON = "don_du_thau"
_DO_TIN_TOI_THIEU = 0.7    # dưới ngưỡng -> KHÔNG dám gate (no-fab)
_DON_CAP = 3000            # trần text đơn dự thầu đưa vào prompt
_MAX_TOKENS = 1024


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
    """Hình thức dự thầu + căn cứ. Xem docstring module cho thứ tự nhánh."""
    by_type = pages_by_type(pages)
    lien_danh_pages = by_type.get(_MA_LIEN_DANH) or []
    co_ttld = bool(lien_danh_pages)
    khai_bao = canon_hinh_thuc(vendor.hinh_thuc) if vendor is not None else HINH_THUC_KHONG_RO

    if khai_bao:
        ho_so_noi = HINH_THUC_LIEN_DANH if co_ttld else HINH_THUC_DOC_LAP
        if khai_bao == ho_so_noi:                                    # (a)
            return VendorProfile(hinh_thuc=khai_bao, nguon=NGUON_KHAI_BAO, do_tin=1.0)
        # (b) MÂU THUẪN -> fail-safe: KHÔNG đoán bên nào đúng, không gate.
        chi_tiet = (f"HSDT CÓ hồ sơ '{_MA_LIEN_DANH}' ({lien_danh_pages[0].file})" if co_ttld
                    else f"HSDT KHÔNG có hồ sơ '{_MA_LIEN_DANH}'")
        return VendorProfile(
            hinh_thuc=HINH_THUC_KHONG_RO, nguon=NGUON_KHONG_DU_CAN_CU, mau_thuan=True,
            ghi_chu=(f"khai báo hình thức '{khai_bao}' nhưng {chi_tiet} — hình thức đặt KHÔNG RÕ, "
                     f"mọi nội dung liên danh VẪN được chấm đầy đủ; cần chuyên gia xác minh"))

    if co_ttld:                                                      # (c)
        return VendorProfile(
            hinh_thuc=HINH_THUC_LIEN_DANH, nguon=NGUON_HO_SO, do_tin=1.0,
            bang_chung=f"HSDT có hồ sơ '{_MA_LIEN_DANH}' ({lien_danh_pages[0].file})",
            trang=[p.trang for p in lien_danh_pages])

    don_pages = by_type.get(_MA_DON) or []
    if don_pages:                                                    # (d)
        return await _detect_tu_don(don_pages, vision_fn, vendor)

    return VendorProfile()                                           # (e)


async def _detect_tu_don(don_pages: list[PageRecord], vision_fn: VisionFn,
                         vendor: VendorContext | None) -> VendorProfile:
    """1 call text-only đọc đơn dự thầu. Mọi đường lỗi/mơ hồ -> '' (không rõ), KHÔNG đoán."""
    out = await vision_fn(SYS_VENDOR_FORM,
                          vendor_form_prompt(pages_text(don_pages)[:_DON_CAP], vendor),
                          validate=validate_vendor_form, max_tokens=_MAX_TOKENS)
    if out.status == "error":
        return VendorProfile(ghi_chu=f"AI lỗi khi đọc đơn dự thầu: {out.error}")
    d = out.data
    hinh_thuc = canon_hinh_thuc(d.get("hinh_thuc", ""))
    bang_chung = d.get("bang_chung", "")
    trang = [int(t) for t in d.get("trang", []) if str(t).isdigit()]
    do_tin = float(d.get("do_tin", 0.0) or 0.0)
    if not hinh_thuc:
        return VendorProfile(bang_chung=bang_chung, trang=trang,
                             ghi_chu="AI không kết luận được hình thức từ đơn dự thầu")
    if do_tin < _DO_TIN_TOI_THIEU:
        return VendorProfile(
            bang_chung=bang_chung, trang=trang,
            ghi_chu=(f"AI đọc đơn ra '{hinh_thuc}' nhưng độ tin {do_tin:.2f} < "
                     f"{_DO_TIN_TOI_THIEU} — không đủ chắc để bỏ qua kiểm tra"))
    return VendorProfile(hinh_thuc=hinh_thuc, nguon=NGUON_DON_DU_THAU, bang_chung=bang_chung,
                         trang=trang, do_tin=do_tin, ghi_chu=d.get("ghi_chu", ""))
