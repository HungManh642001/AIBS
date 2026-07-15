"""Tầng C+D — đánh giá từng nội dung (đối chiếu HSDT vs chuẩn HSMT) + roll-up tiêu chí."""
from __future__ import annotations

import logging
from typing import Any

from experiment.evaluate.prompts import SYS_EVAL, eval_prompt
from experiment.evaluate.route import _norm, loc_dung_chung, pages_by_type, pages_text, route_pages
from experiment.evaluate.rules.registry import RuleRegistry, RuleSkill, run_skill
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
        nguon_hsmt=nd.get("nguon", ""),   # 1 chỗ -> phủ MỌI đường verdict (đạt/thiếu/review/N/A)
    )


def _types_khac(nd: dict[str, Any], extra_types: list[str] | None) -> list[str]:
    """Các tài liệu ĐỐI CHIẾU tiêu chí khai thêm, ngoài hồ sơ chính của nội dung này."""
    main = _norm(nd.get("hsdt_kiem_tra", ""))
    return [str(t) for t in (extra_types or []) if _norm(str(t)) != main]


def _cross_text(nd: dict[str, Any], matched: list[PageRecord], pages: list[PageRecord],
                extra_types: list[str], vendor_ctx: VendorContext | None = None) -> str:
    """Đối chiếu chéo: khối text theo TỪNG loại hồ sơ, cap per-type (trùng hồ sơ chính bị dedup).

    Tài liệu dùng chung được lọc về đúng nhà thầu đang chấm TRƯỚC khi vào prompt (loc_dung_chung).
    """
    main = nd.get("hsdt_kiem_tra", "")
    blocks = [f"[HỒ SƠ: {main}]\n{pages_text(matched)[:_CROSS_TYPE_CAP]}"]
    seen = {id(p) for p in matched}
    for t in extra_types:
        ps = [p for p in route_pages(pages, str(t)) if id(p) not in seen]
        ps = loc_dung_chung(ps, str(t), vendor_ctx)
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


def _gate_khong_ap_dung(nd: dict[str, Any], profile: VendorProfile | None,
                        crit: dict[str, Any] | None = None) -> Verdict | None:
    """Nhà thầu ĐỘC LẬP + tiêu chí dính hồ sơ chỉ-liên-danh -> N/A tất định, 0 call AI.

    Xét CẢ hsdt_kiem_tra của nội dung LẪN hsdt_can_kiem_tra của tiêu chí: yêu cầu kiểu 'Đối với nhà
    thầu liên danh, đơn phải ký theo phân công trong thỏa thuận' có hsdt_kiem_tra='don_du_thau'
    nhưng khai thỏa thuận liên danh làm tài liệu đối chiếu — không xét cấp tiêu chí thì phải nhờ AI
    tự nhận ra, tốn call và không chắc chắn.

    Dựa trên QUY TẮC NGUYÊN TỬ: tiêu chí khai thoa_thuan_lien_danh là tiêu chí về nhánh liên danh.
    Báo cáo in nguyên văn yêu cầu gốc bị bỏ qua để chuyên gia bắt lỗi nếu decompose gộp nhầm.
    profile=None hoặc hình thức không rõ -> None (không gate) = hành vi cũ, fail-safe.
    """
    if profile is None or profile.hinh_thuc != HINH_THUC_DOC_LAP:
        return None
    dinh = {_norm(nd.get("hsdt_kiem_tra", ""))}
    dinh |= {_norm(str(x)) for x in (crit or {}).get("hsdt_can_kiem_tra", [])}
    if not (dinh & _HO_SO_CHI_LIEN_DANH):
        return None
    goc = str((crit or {}).get("yeu_cau_goc", "")).strip()
    trich = f'; yêu cầu gốc bị bỏ qua: "{goc}"' if goc else ""
    return _verdict(nd, KET_QUA_KHONG_AP_DUNG, do_tin=profile.do_tin,
                    ghi_chu=(f"{_can_cu_doc_lap(profile)} — nội dung này gắn hồ sơ 'thỏa thuận "
                             f"liên danh', chỉ áp dụng cho nhà thầu liên danh{trich}"))


def _skill_cho_nd(skills: list[RuleSkill], nd: dict[str, Any]) -> RuleSkill | None:
    """Luật phục vụ nội dung route tới BẤT KỲ hồ sơ nào trong bộ ho_so_can của nó.

    Khớp theo THÀNH VIÊN (không chỉ ho_so_can[0]): luật đọc cả bộ hồ sơ nên trả lời được dù STRUCT
    chọn hsdt_kiem_tra là hồ sơ chính hay tài liệu đối chiếu. Quan trọng với tài liệu DÙNG CHUNG —
    nếu để rơi xuống eval chung thì prompt sẽ nuốt trọn webform của MỌI nhà thầu.

    Giả định (QUY TẮC NGUYÊN TỬ của decompose): tiêu chí khai đủ bộ hồ sơ của luật chính là tiêu chí
    về phép đối chiếu đó. Nội dung route tới hồ sơ ngoài bộ vẫn chạy eval chung.
    """
    key = _norm(nd.get("hsdt_kiem_tra", ""))
    for s in skills:
        if key and key in {_norm(h) for h in s.ho_so_can}:
            return s
    return None


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
    main = nd.get("hsdt_kiem_tra", "")
    matched = route_pages(pages, main)
    if not matched:
        return _verdict(nd, KET_QUA_THIEU, bang_chung=f"HSDT không có: {main}",
                        ghi_chu="thiếu hồ sơ tương ứng")
    loc = loc_dung_chung(matched, main, vendor_ctx)   # chống lộ dữ liệu nhà thầu khác vào prompt
    if not loc:
        return _verdict(nd, KET_QUA_SOI, ghi_chu=(
            f"'{main}' là tài liệu dùng chung cả gói — "
            + (f"không dò được dòng nhà thầu '{vendor_ctx.ten}'" if vendor_ctx is not None
               else "thiếu ngữ cảnh nhà thầu (tên/MST) để lọc đúng dòng")))
    matched = loc
    # Tín hiệu cross = tiêu chí KHAI tài liệu ngoài hồ sơ chính (SYS_LIST dạy khai tài liệu đối
    # chiếu). KHÔNG bám vào cờ doi_chieu_hsdt: cờ đó chỉ bật khi RESOLVE trả thuoc_hsdt, mà RESOLVE
    # chỉ chạy khi can_tra_cuu=True — trong khi SYS_STRUCT dạy nội dung thuộc hồ sơ nhà thầu thì
    # can_tra_cuu=False -> cờ không bao giờ bật cho đúng ca cần đối chiếu chéo.
    khac = _types_khac(nd, extra_types)
    cross = bool(khac)
    text = _cross_text(nd, matched, pages, khac, vendor_ctx) if cross else pages_text(matched)
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
                             by_type: dict[str, list[PageRecord]] | None = None) -> CriterionEval:
    """Đánh giá mọi nội dung của 1 tiêu chí + roll-up.

    tien_quyet + không đạt -> loại. Verdict 'không áp dụng' TRUNG TÍNH: không kéo tiêu chí xuống
    'cần làm rõ', không tính là 'đạt'; toàn bộ N/A -> tiêu chí N/A (loai=False dù tiên quyết) —
    nhưng KHÔNG che 'không đạt'.

    Luật (registry): tiêu chí khai đủ `ho_so_can` của luật -> luật THAY THẾ kết luận của nội dung
    route tới `ho_so_can[0]` (không gọi eval chung cho nội dung đó). Phải thay thế chứ không bổ
    sung: eval chung chỉ đọc được hồ sơ chính nên trả 'cần làm rõ', mà 'cần làm rõ' thắng 'đạt'
    trong roll-up -> verdict luật sẽ bị vô hiệu.
    """
    ten = crit.get("ten", "")
    log.info("  [eval] %s", ten)
    verdicts: list[Verdict] = []
    nds = crit.get("noi_dung_can_kiem_tra", [])
    ten_nds = [str(n.get("noi_dung_kiem_tra", "")) for n in nds]
    skills = registry.matching(crit) if registry is not None else []
    by_type_ = by_type if by_type is not None else pages_by_type(pages)
    for i, nd in enumerate(nds):
        gated = _gate_khong_ap_dung(nd, profile, crit)   # N/A trước luật: khỏi tốn call
        if gated is not None:
            verdicts.append(gated)
            continue
        skill = _skill_cho_nd(skills, nd)
        if skill is not None:
            verdicts.append(await run_skill(skill, by_type_, vendor_ctx, crit, vision_fn, nd=nd))
            continue
        extra = crit.get("hsdt_can_kiem_tra", [])   # eval tự lọc ra tài liệu ngoài hồ sơ chính
        anh_em = [t for j, t in enumerate(ten_nds) if j != i and t]   # 1 gốc -> N need: phân công rõ
        verdicts.append(await eval_noi_dung(nd, pages, vision_fn, extra_types=extra,
                                            vendor_ctx=vendor_ctx, profile=profile,
                                            yeu_cau_goc=str(crit.get("yeu_cau_goc", "")),
                                            anh_em=anh_em or None))
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
                         ket_qua=ket_qua, loai=loai, verdicts=verdicts,
                         yeu_cau_goc=str(crit.get("yeu_cau_goc", "")))
