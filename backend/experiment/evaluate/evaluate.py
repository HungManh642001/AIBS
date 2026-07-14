"""Tầng C+D — đánh giá từng nội dung (đối chiếu HSDT vs chuẩn HSMT) + roll-up tiêu chí."""
from __future__ import annotations

import logging
from typing import Any

from experiment.evaluate.prompts import SYS_EVAL, eval_prompt
from experiment.evaluate.route import _norm, pages_by_type, pages_text, route_pages
from experiment.evaluate.rules.registry import RuleRegistry, dispatch_rules
from experiment.evaluate.schema import (
    HINH_THUC_DOC_LAP,
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_KHONG_AP_DUNG, KET_QUA_LOI, KET_QUA_SOI, KET_QUA_THIEU,
    CriterionEval, PageRecord, VendorContext, VendorProfile, Verdict, validate_eval_verdict,
)
from experiment.evaluate.vision import VisionFn

log = logging.getLogger("experiment.evaluate")
_KET_QUA_HOP_LE = {KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_SOI}
_EVAL_MAX_TOKENS = 4096
_CROSS_TYPE_CAP = 3000  # trần text MỖI loại hồ sơ khi đối chiếu chéo (thay [:6000] toàn cục)
_HO_SO_CHI_LIEN_DANH = {"thoa_thuan_lien_danh"}   # hồ sơ CHỈ nhà thầu liên danh mới phải nộp


def _verdict(nd: dict[str, Any], ket_qua: str, bang_chung: str = "",
             trang: list[int] | None = None, do_tin: float = 0.0, ghi_chu: str = "") -> Verdict:
    return Verdict(
        noi_dung_kiem_tra=nd.get("noi_dung_kiem_tra", ""), hsdt_kiem_tra=nd.get("hsdt_kiem_tra", ""),
        yeu_cau=nd.get("yeu_cau", ""), thong_tin_bo_sung=nd.get("thong_tin_bo_sung", ""),
        ket_qua=ket_qua, bang_chung=bang_chung, trang=trang or [], do_tin=do_tin, ghi_chu=ghi_chu,
    )


def _cross_text(nd: dict[str, Any], matched: list[PageRecord], pages: list[PageRecord],
                extra_types: list[str]) -> str:
    """Đối chiếu chéo (doi_chieu_hsdt): khối text theo TỪNG loại hồ sơ, cap per-type."""
    main = nd.get("hsdt_kiem_tra", "")
    blocks = [f"[HỒ SƠ: {main}]\n{pages_text(matched)[:_CROSS_TYPE_CAP]}"]
    seen = {id(p) for p in matched}
    for t in extra_types:
        ps = [p for p in route_pages(pages, str(t)) if id(p) not in seen]
        if ps:
            seen.update(id(p) for p in ps)
            blocks.append(f"[HỒ SƠ: {t}]\n{pages_text(ps)[:_CROSS_TYPE_CAP]}")
    return "\n\n".join(blocks)


def _allowed_ket_qua(profile: VendorProfile | None) -> set[str]:
    """'không áp dụng' CHỈ hợp lệ khi CODE đã xác định nhà thầu độc lập — không tin AI tự khai."""
    if profile is not None and profile.hinh_thuc == HINH_THUC_DOC_LAP:
        return _KET_QUA_HOP_LE | {KET_QUA_KHONG_AP_DUNG}
    return _KET_QUA_HOP_LE


def _can_cu_doc_lap(profile: VendorProfile) -> str:
    can_cu = f"căn cứ: {profile.nguon}"
    if profile.bang_chung:
        can_cu += f"; {profile.bang_chung}"
    return f"nhà thầu dự thầu theo hình thức độc lập ({can_cu})"


def _gate_khong_ap_dung(nd: dict[str, Any], profile: VendorProfile | None) -> Verdict | None:
    """Nhà thầu ĐỘC LẬP + hồ sơ chỉ dành cho liên danh -> N/A tất định, 0 call AI.

    profile=None hoặc hình thức không rõ -> None (không gate) = hành vi cũ, fail-safe.
    """
    if profile is None or profile.hinh_thuc != HINH_THUC_DOC_LAP:
        return None
    if _norm(nd.get("hsdt_kiem_tra", "")) not in _HO_SO_CHI_LIEN_DANH:
        return None
    return _verdict(nd, KET_QUA_KHONG_AP_DUNG, do_tin=profile.do_tin,
                    ghi_chu=(f"{_can_cu_doc_lap(profile)} — hồ sơ 'thỏa thuận liên danh' chỉ áp "
                             f"dụng cho nhà thầu liên danh"))


async def eval_noi_dung(nd: dict[str, Any], pages: list[PageRecord], vision_fn: VisionFn,
                        *, extra_types: list[str] | None = None,
                        vendor_ctx: VendorContext | None = None,
                        profile: VendorProfile | None = None,
                        yeu_cau_goc: str = "", anh_em: list[str] | None = None) -> Verdict:
    """1 nội dung kiểm tra -> verdict (route + đối chiếu THUẦN TEXT; chữ ký/dấu đã có trong text ingest).

    extra_types (need doi_chieu_hsdt): các loại hồ sơ khác của tiêu chí để đối chiếu chéo trong HSDT.
    profile: hình thức dự thầu -> gate 'không áp dụng' (đặt TRƯỚC can_review: N/A thông tin hơn).
    yeu_cau_goc/anh_em: chống lạm phát yêu cầu + trôi phạm vi — xem eval_prompt.

    GIỚI HẠN: nhánh can_review short-circuit 0 call, nên yeu_cau_goc KHÔNG cứu được need mà
    decompose bịa can_lam_ro cho thứ HSMT không đòi — bệnh đó phải chữa ở SYS_STRUCT.
    """
    gated = _gate_khong_ap_dung(nd, profile)
    if gated is not None:
        return gated
    if nd.get("can_review") and not (nd.get("thong_tin_bo_sung") or "").strip():
        # Chuẩn HSMT chưa tra được (decompose cờ can_review) -> không có căn cứ đối chiếu (no-fab).
        return _verdict(nd, KET_QUA_SOI, ghi_chu="chuẩn HSMT chưa tra được — cần chuyên gia đối chiếu")
    matched = route_pages(pages, nd.get("hsdt_kiem_tra", ""))
    if not matched:
        return _verdict(nd, KET_QUA_THIEU, bang_chung=f"HSDT không có: {nd.get('hsdt_kiem_tra', '')}",
                        ghi_chu="thiếu hồ sơ tương ứng")
    cross = bool(nd.get("doi_chieu_hsdt") and extra_types)
    text = _cross_text(nd, matched, pages, [str(t) for t in extra_types]) if cross \
        else pages_text(matched)
    out = await vision_fn(SYS_EVAL, eval_prompt(nd, text, cross=cross, vendor_ctx=vendor_ctx,
                                                profile=profile, yeu_cau_goc=yeu_cau_goc,
                                                anh_em=anh_em),
                          validate=validate_eval_verdict, max_tokens=_EVAL_MAX_TOKENS)
    if out.status == "error":
        return _verdict(nd, KET_QUA_LOI, bang_chung=f"AI lỗi: {out.error}", ghi_chu="cần soi lại")
    d = out.data
    ket_qua = d.get("ket_qua", KET_QUA_SOI)
    if ket_qua not in _allowed_ket_qua(profile):   # AI tự khai N/A khi chưa rõ hình thức -> chặn
        ket_qua = KET_QUA_SOI
    ghi_chu = d.get("ghi_chu", "")
    if ket_qua == KET_QUA_KHONG_AP_DUNG and not ghi_chu.strip() and profile is not None:
        ghi_chu = _can_cu_doc_lap(profile)        # AI quên nêu căn cứ -> điền căn cứ ĐÃ BIẾT
    return _verdict(nd, ket_qua, bang_chung=d.get("bang_chung", ""),
                    trang=[int(t) for t in d.get("trang", []) if str(t).isdigit()],
                    do_tin=float(d.get("do_tin", 0.0) or 0.0), ghi_chu=ghi_chu)


async def evaluate_criterion(crit: dict[str, Any], pages: list[PageRecord],
                             vision_fn: VisionFn, *,
                             registry: RuleRegistry | None = None,
                             vendor_ctx: VendorContext | None = None,
                             profile: VendorProfile | None = None,
                             by_type: dict[str, list[PageRecord]] | None = None,
                             fired: set[str] | None = None) -> CriterionEval:
    """Đánh giá mọi nội dung của 1 tiêu chí + verdict luật (nếu có registry) + roll-up.

    tien_quyet + không đạt -> loại. Luật bắn 1 lần/vendor ở tiêu chí ĐẦU TIÊN khớp kich_hoat
    (caller giữ `fired` xuyên các tiêu chí); verdict luật vào chung roll-up.
    Verdict 'không áp dụng' TRUNG TÍNH: không kéo tiêu chí xuống 'cần làm rõ', không tính là 'đạt';
    toàn bộ N/A -> tiêu chí N/A (loai=False dù tiên quyết) — nhưng KHÔNG che 'không đạt'.
    """
    ten = crit.get("ten", "")
    log.info("  [eval] %s", ten)
    verdicts: list[Verdict] = []
    nds = crit.get("noi_dung_can_kiem_tra", [])
    ten_nds = [str(n.get("noi_dung_kiem_tra", "")) for n in nds]
    for i, nd in enumerate(nds):
        extra = crit.get("hsdt_can_kiem_tra", []) if nd.get("doi_chieu_hsdt") else None
        anh_em = [t for j, t in enumerate(ten_nds) if j != i and t]   # 1 gốc -> N need: phân công rõ
        verdicts.append(await eval_noi_dung(nd, pages, vision_fn, extra_types=extra,
                                            vendor_ctx=vendor_ctx, profile=profile,
                                            yeu_cau_goc=str(crit.get("yeu_cau_goc", "")),
                                            anh_em=anh_em or None))
    if registry is not None:
        verdicts.extend(await dispatch_rules(
            registry, crit, by_type if by_type is not None else pages_by_type(pages),
            vendor_ctx, vision_fn, fired if fired is not None else set()))
    xet = [v for v in verdicts if v.ket_qua != KET_QUA_KHONG_AP_DUNG]   # N/A trung tính
    kq = {v.ket_qua for v in xet}
    if KET_QUA_KHONG in kq:
        ket_qua = KET_QUA_KHONG
    elif kq & {KET_QUA_SOI, KET_QUA_THIEU, KET_QUA_LOI}:
        ket_qua = KET_QUA_SOI
    elif kq == {KET_QUA_DAT}:
        ket_qua = KET_QUA_DAT
    elif verdicts and not xet:          # có verdict nhưng TẤT CẢ đều N/A
        ket_qua = KET_QUA_KHONG_AP_DUNG
    else:                               # verdicts rỗng -> giữ hành vi cũ
        ket_qua = KET_QUA_SOI
    loai = ket_qua == KET_QUA_KHONG and bool(crit.get("tien_quyet"))
    return CriterionEval(nhom=crit.get("nhom", "hop_le"), ten=ten, tien_quyet=bool(crit.get("tien_quyet")),
                         ket_qua=ket_qua, loai=loai, verdicts=verdicts)
