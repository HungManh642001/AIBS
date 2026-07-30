"""Tầng C+D — đánh giá từng nội dung (đối chiếu HSDT vs chuẩn HSMT) + roll-up tiêu chí."""
from __future__ import annotations

from typing import Any

from services import artifact_catalog

from experiment.evaluate.prompts import SYS_EVAL, eval_prompt
from experiment.evaluate.route import _norm, loc_dung_chung, pages_by_type, pages_text, route_pages
from experiment.evaluate.rules.registry import RuleRegistry, RuleSkill, run_skill
from experiment.evaluate.schema import (
    HINH_THUC_DOC_LAP, HINH_THUC_LIEN_DANH, KET_LUAN_KHONG_AP_DUNG,
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_KHONG_AP_DUNG, KET_QUA_LOI, KET_QUA_SOI, KET_QUA_THIEU,
    CriterionEval, PageRecord, VendorContext, VendorProfile, Verdict, validate_eval_verdict,
)
from experiment.evaluate.vendor_profile import canon_hinh_thuc
from experiment.evaluate.vision import VisionFn

from experiment.logger_config import setup_logger
log = setup_logger('EVALUATE', 'evaluate.log')

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
    blocks = [f"[HỒ SƠ: {main}]\n{pages_text(matched)}"]
    seen = {id(p) for p in matched}
    for t in extra_types:
        ps = [p for p in route_pages(pages, str(t)) if id(p) not in seen]
        ps = loc_dung_chung(ps, str(t), vendor_ctx)
        if ps:
            seen.update(id(p) for p in ps)
            blocks.append(f"[HỒ SƠ: {t}]\n{pages_text(ps)}")
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
    """Nội dung CHỈ áp dụng 1 hình thức + nhà thầu hình thức KHÁC -> N/A tất định, 0 call AI.

    Tín hiệu áp dụng ở CẤP NỘI DUNG (không phải cấp tiêu chí): trường `ap_dung` do decompose gán,
    HOẶC nội dung route thẳng vào hồ sơ chỉ-liên-danh (thoa_thuan_lien_danh) -> hiển nhiên liên danh.
    KHÔNG xét crit['hsdt_can_kiem_tra']: MỘT tiêu chí có thể TRỘN nội dung chung (mọi nhà thầu) với
    nội dung điều kiện liên danh; gate cả tiêu chí sẽ bỏ sót nội dung chung (vd 'đơn ký bởi đại diện
    hợp pháp' áp dụng mọi nhà thầu, không được bỏ khi nhà thầu độc lập).

    profile=None / hình thức không rõ -> None (fail-safe: chấm, không im lặng bỏ). Báo cáo in
    nguyên văn yêu cầu gốc bị bỏ qua để chuyên gia bắt lỗi nếu decompose gán ap_dung sai.
    """
    # (1) Điều kiện theo GIÁ TRỊ do decompose đã đối chiếu tất định (vd giá trị bảo đảm dự thầu
    # 939 triệu, trong khi nội dung chỉ áp dụng khi < 50 triệu). KHÔNG phụ thuộc hình thức nhà
    # thầu -> phải xét TRƯỚC nhánh profile=None, nếu không prod (hsdt_pipeline không truyền
    # profile) sẽ bỏ qua toàn bộ cơ chế này.
    dk = nd.get("dieu_kien_ap_dung") or {}
    if dk.get("ket_luan") == KET_LUAN_KHONG_AP_DUNG:
        return _verdict(nd, KET_QUA_KHONG_AP_DUNG, do_tin=1.0,
                        ghi_chu=f"điều kiện áp dụng của HSMT không thoả — {dk.get('can_cu', '')}")

    # (2) Điều kiện theo HÌNH THỨC nhà thầu — cần biết hình thức mới quyết được.
    if profile is None or not profile.hinh_thuc:
        return None
    ap = canon_hinh_thuc(nd.get("ap_dung", ""))   # -> "độc lập" | "liên danh" | ""
    chi_lien_danh = ap == HINH_THUC_LIEN_DANH or _norm(nd.get("hsdt_kiem_tra", "")) in _HO_SO_CHI_LIEN_DANH
    chi_doc_lap = ap == HINH_THUC_DOC_LAP
    if profile.hinh_thuc == HINH_THUC_DOC_LAP and chi_lien_danh:
        khac = HINH_THUC_LIEN_DANH
    elif profile.hinh_thuc == HINH_THUC_LIEN_DANH and chi_doc_lap:
        khac = HINH_THUC_DOC_LAP
    else:
        return None
    goc = str((crit or {}).get("yeu_cau_goc", "")).strip()
    trich = f'; yêu cầu gốc bị bỏ qua: "{goc}"' if goc else ""
    return _verdict(nd, KET_QUA_KHONG_AP_DUNG, do_tin=profile.do_tin,
                    ghi_chu=(f"nhà thầu dự thầu theo hình thức {profile.hinh_thuc} "
                             f"(căn cứ: {profile.nguon}) — nội dung này chỉ áp dụng cho nhà thầu "
                             f"{khac}{trich}"))


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


def _bo_ho_so_nd(nd: dict[str, Any]) -> set[str]:
    """Bộ hồ sơ mà NỘI DUNG này tự khai: hồ sơ chính + tài liệu đối chiếu riêng của nó."""
    bo = {_norm(str(t)) for t in (nd.get("hsdt_doi_chieu") or [])}
    bo.add(_norm(nd.get("hsdt_kiem_tra", "")))
    return bo - {""}


def _nd_nhac_doi_chieu(skill: RuleSkill, nd: dict[str, Any]) -> bool:
    """Nội dung có NHẮC mọi tài liệu đối chiếu của luật (ngoài hồ sơ chính của chính nó) không?"""
    chinh = _norm(nd.get("hsdt_kiem_tra", ""))
    khac = [h for h in skill.ho_so_can if _norm(h) != chinh]
    if not khac:
        return True
    text = f"{nd.get('noi_dung_kiem_tra', '')} {nd.get('yeu_cau', '')}"
    return all(artifact_catalog.nhac_toi(text, str(h)) for h in khac)


def _phan_luat_cho_nd(skills: list[RuleSkill],
                      nds: list[dict[str, Any]]) -> dict[int, RuleSkill]:
    """Chỉ số nội dung -> luật phục vụ nó. Chỉ PHÂN XỬ khi một luật có NHIỀU ứng viên.

    Một yêu cầu gốc của HSMT có thể sinh nhiều nội dung trên CÙNG hồ sơ chính (gói 54: "phải nộp
    Bảng chào giá đúng Mẫu 05C.1" + "giá phải phù hợp webform" đều route tới bang_gia). Khớp theo
    thành viên `ho_so_can` thì cả hai cùng dính luật -> nội dung mẫu biểu bị chấm bằng phép so giá,
    và `thong_tin_bo_sung` (chuẩn 14 cột đã resolve từ HSMT) bị vứt bỏ.

    Chỉ có MỘT ứng viên -> KHÔNG đụng gì, giữ nguyên hành vi (kể cả khi STRUCT chọn hsdt_kiem_tra
    là tài liệu đối chiếu — rơi xuống eval chung thì prompt nuốt webform của MỌI nhà thầu).
    Từ HAI ứng viên -> phân xử 3 tầng: metadata nội dung tự khai -> từ khóa nhắc tài liệu đối
    chiếu -> fail-safe giữ tất cả (thà thừa còn hơn âm thầm mất luật).
    """
    gan: dict[int, RuleSkill] = {}
    for s in skills:
        ung_vien = [i for i, nd in enumerate(nds) if _skill_cho_nd([s], nd) is not None]
        if len(ung_vien) > 1:
            loc = [i for i in ung_vien if set(_norm(h) for h in s.ho_so_can) <= _bo_ho_so_nd(nds[i])]
            if not loc:
                loc = [i for i in ung_vien if _nd_nhac_doi_chieu(s, nds[i])]
            if loc:
                ung_vien = loc
            else:
                log.warning("  [eval] luật %s có %d nội dung ứng viên nhưng không phân xử được — "
                            "giữ tất cả", s.id, len(ung_vien))
        for i in ung_vien:
            gan.setdefault(i, s)
    return gan


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

    Verdict 'không áp dụng' TRUNG TÍNH: không kéo tiêu chí xuống
    'cần làm rõ', không tính là 'đạt'; toàn bộ N/A -> tiêu chí N/A —
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
    luat_cho_nd = _phan_luat_cho_nd(skills, nds)
    by_type_ = by_type if by_type is not None else pages_by_type(pages)
    for i, nd in enumerate(nds):
        gated = _gate_khong_ap_dung(nd, profile, crit)   # N/A trước luật: khỏi tốn call
        if gated is not None:
            verdicts.append(gated)
            continue
        skill = luat_cho_nd.get(i)
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
    return CriterionEval(nhom=crit.get("nhom", "hop_le"), ten=ten,
                         ket_qua=ket_qua, verdicts=verdicts,
                         yeu_cau_goc=str(crit.get("yeu_cau_goc", "")))
