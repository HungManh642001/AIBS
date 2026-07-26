"""Luật: bảng phân công trong THỎA THUẬN LIÊN DANH phải nêu rõ hạng mục và khớp tỷ lệ bảng giá.

Hai điều kiện (điều kiện 1 là TIỀN ĐỀ của điều kiện 2 — không nêu rõ hạng mục thì không có gì để
cộng tiền):
1. Nội dung công việc từng thành viên phải nêu RÕ hạng mục nào trong bảng giá (không chấp nhận
   "cung cấp hàng hóa", "phần thiết bị" chung chung).
2. Cột "tỷ lệ % giá trị đảm nhận" phải bằng: tổng thành tiền các hạng mục thành viên đó đảm nhận
   / tổng giá trị hàng hóa của liên danh, dung sai `DUNG_SAI_DIEM_PT` điểm phần trăm.

STANDING CHECK (pham_vi="goi"): verdict ra `EvalResult.phat_hien_bo_sung`, ngoài roll-up.
Không có thỏa thuận liên danh -> 'không áp dụng' (nhà thầu độc lập), KHÔNG gọi LLM.

PHÂN VAI: LLM chỉ BÓC dữ liệu (hạng mục, thành tiền, tỷ lệ khai) — KHÔNG tính, KHÔNG kết luận;
`doi_chieu_phan_cong` (hàm thuần) làm số học và ra kết luận. Số học của LLM không đáng tin, còn
việc đọc bảng scan thì code không làm được — mỗi bên làm đúng phần mạnh của mình.
"""
from __future__ import annotations

from typing import Any

from services.prompts import cot_block

from experiment.evaluate.route import pages_text
from experiment.evaluate.rules.registry import PHAM_VI_GOI, RuleSkill
from experiment.evaluate.schema import (
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_KHONG_AP_DUNG, KET_QUA_LOI, KET_QUA_SOI, KET_QUA_THIEU,
    PageRecord, VendorContext, Verdict, _Base,
)

_TEN = "Phân công liên danh nêu rõ hạng mục và khớp tỷ lệ trong bảng giá"
_TTLD = "thoa_thuan_lien_danh"
_GIA = "bang_gia"
_HO_SO = [_TTLD, _GIA]
_TTLD_CAP = 3000      # trần text thỏa thuận liên danh
_GIA_CAP = 6000       # bảng giá cần ĐỦ hạng mục + thành tiền -> nới rộng hơn
_MAX_TOKENS = 4096

DUNG_SAI_DIEM_PT = 0.1      # lệch tối đa cho phép giữa tỷ lệ khai và tỷ lệ tính (điểm %)
_LECH_TONG_TOI_DA = 0.02    # Σ tiền thành viên vs tổng liên danh: lệch >2% -> nghi bóc thiếu

SYS_RULE_LIEN_DANH = (
    "Bạn là chuyên gia chấm thầu. Đọc BẢNG PHÂN CÔNG TRÁCH NHIỆM trong thỏa thuận liên danh và "
    "BẢNG GIÁ dự thầu, rồi BÓC DỮ LIỆU (KHÔNG tính toán, KHÔNG kết luận đạt/không đạt — phần đó "
    "hệ thống tự làm):\n"
    "- tong_gia_tri_lien_danh: TỔNG giá trị hàng hóa cung cấp của liên danh theo bảng giá.\n"
    "- Mỗi thành viên: ten; mo_ta_cong_viec (nguyên văn cột nội dung công việc đảm nhận); "
    "neu_ro_hang_muc = true CHỈ KHI mô tả chỉ đích danh được hạng mục trong bảng giá (tên/mã hạng "
    "mục), false nếu chỉ ghi chung chung ('cung cấp hàng hóa', 'phần thiết bị', 'thi công lắp "
    "đặt'); hang_muc: các hạng mục thành viên đó đảm nhận kèm thanh_tien LẤY TỪ BẢNG GIÁ; "
    "tong_tien: tổng thành tiền các hạng mục đó; ty_le_khai: số % ghi ở cột tỷ lệ giá trị đảm "
    "nhận trong thỏa thuận (chỉ con số, vd 60.0).\n"
    "neu_ro_hang_muc=false thì để hang_muc rỗng và tong_tien=0. TUYỆT ĐỐI KHÔNG bịa hạng mục, "
    "không bịa số tiền, không tự suy ra tỷ lệ khi thỏa thuận không ghi. Chỉ trả JSON."
)


class HangMuc(_Base):
    ten: str = ""
    thanh_tien: float = 0.0


class ThanhVienPhanCong(_Base):
    ten: str = ""
    mo_ta_cong_viec: str = ""
    neu_ro_hang_muc: bool = False
    hang_muc: list[HangMuc] = []
    tong_tien: float = 0.0
    ty_le_khai: float = 0.0


class PhanCongOut(_Base):
    tong_gia_tri_lien_danh: float = 0.0
    thanh_vien: list[ThanhVienPhanCong] = []
    trang: list[int] = []
    ghi_chu: str = ""


def validate_phan_cong(d: dict[str, Any]) -> dict[str, Any]:
    return PhanCongOut(**d).model_dump()


def lien_danh_prompt(ttld_text: str, gia_text: str) -> str:
    return (
        "[RULE:lien_danh_phan_cong]\n"
        f"THỎA THUẬN LIÊN DANH (bóc từ ảnh):\n{ttld_text[:_TTLD_CAP]}\n\n"
        f"BẢNG GIÁ DỰ THẦU (bóc từ ảnh):\n{gia_text[:_GIA_CAP]}\n\n"
        + cot_block('{"tong_gia_tri_lien_danh":0,"thanh_vien":[{"ten":"...",'
                    '"mo_ta_cong_viec":"<nguyên văn>","neu_ro_hang_muc":true,'
                    '"hang_muc":[{"ten":"...","thanh_tien":0}],"tong_tien":0,"ty_le_khai":0.0}],'
                    '"trang":[...],"ghi_chu":""}')
    )


def _pt(x: float) -> str:
    """Số phần trăm kiểu Việt: 1 chữ số thập phân, dấu phẩy."""
    return f"{x:.1f}".replace(".", ",") + "%"


def _tien(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def doi_chieu_phan_cong(d: dict[str, Any],
                        dung_sai: float = DUNG_SAI_DIEM_PT) -> tuple[str, str, str]:
    """Dữ liệu đã bóc -> (ket_qua, bang_chung, ghi_chu). Hàm THUẦN: mọi số học nằm ở đây.

    Thứ tự kết luận: thiếu căn cứ (tổng/thành viên) -> SOI; Σ tiền lệch tổng liên danh -> SOI;
    có thành viên không nêu rõ hạng mục hoặc lệch tỷ lệ -> KHÔNG ĐẠT; còn lại -> ĐẠT.
    """
    tong = float(d.get("tong_gia_tri_lien_danh", 0.0) or 0.0)
    tvs = d.get("thanh_vien") or []
    if not tvs:
        return KET_QUA_SOI, "", "không bóc được thành viên nào trong bảng phân công liên danh"
    if tong <= 0:
        return KET_QUA_SOI, "", "không đọc được tổng giá trị hàng hóa của liên danh trong bảng giá"

    dong: list[str] = []
    mo_ho: list[str] = []
    lech: list[str] = []
    for tv in tvs:
        ten = tv.get("ten") or "(không rõ tên)"
        khai = float(tv.get("ty_le_khai", 0.0) or 0.0)
        if not tv.get("neu_ro_hang_muc"):
            mo_ho.append(ten)
            dong.append(f"{ten}: '{tv.get('mo_ta_cong_viec', '')}' — KHÔNG nêu rõ hạng mục trong "
                        f"bảng giá (khai {_pt(khai)}) ✗")
            continue
        tien = float(tv.get("tong_tien", 0.0) or 0.0)
        tinh = tien / tong * 100
        hm = " + ".join(h.get("ten", "?") for h in (tv.get("hang_muc") or [])) or "(không nêu)"
        dat = abs(tinh - khai) <= dung_sai
        dong.append(f"{ten}: {hm} = {_tien(tien)} / {_tien(tong)} = {_pt(tinh)} — khai "
                    f"{_pt(khai)} {'✓' if dat else f'✗ lệch {_pt(abs(tinh - khai))[:-1]} điểm %'}")
        if not dat:
            lech.append(ten)

    bang_chung = "; ".join(dong)
    tong_tv = sum(float(tv.get("tong_tien", 0.0) or 0.0) for tv in tvs)
    if abs(tong_tv - tong) / tong > _LECH_TONG_TOI_DA and not mo_ho:
        return (KET_QUA_SOI, bang_chung,
                f"tổng tiền các thành viên ({_tien(tong_tv)}) lệch tổng giá trị liên danh "
                f"({_tien(tong)}) — có thể còn hạng mục chưa phân công hoặc bảng giá bóc thiếu")
    if mo_ho:
        return (KET_QUA_KHONG, bang_chung,
                f"không nêu rõ hạng mục đảm nhận trong bảng giá: {', '.join(mo_ho)}")
    if lech:
        return (KET_QUA_KHONG, bang_chung,
                f"tỷ lệ khai khác tỷ lệ tính từ bảng giá: {', '.join(lech)}")
    return KET_QUA_DAT, bang_chung, ""


def _verdict(ket_qua: str, bang_chung: str = "", trang: list[int] | None = None,
             ghi_chu: str = "") -> Verdict:
    return Verdict(noi_dung_kiem_tra=_TEN, hsdt_kiem_tra=_TTLD,
                   yeu_cau=("Bảng phân công liên danh phải nêu rõ hạng mục đảm nhận trong bảng giá "
                            "và tỷ lệ % giá trị đảm nhận phải khớp giá trị hạng mục đó"),
                   thong_tin_bo_sung="", ket_qua=ket_qua, bang_chung=bang_chung,
                   trang=trang or [], do_tin=0.0, ghi_chu=ghi_chu, nguon_doc=list(_HO_SO))


async def handler(by_type: dict[str, list[PageRecord]], vendor_ctx: VendorContext | None,
                  criterion: dict[str, Any], vision_fn: Any,
                  *, nd: dict[str, Any] | None = None, pkg: Any = None) -> Verdict:
    # standing check: không phục vụ nội dung nào -> bỏ qua nd; không cần ngữ cảnh gói -> bỏ qua pkg.
    if not by_type.get(_TTLD):
        return _verdict(KET_QUA_KHONG_AP_DUNG,
                        ghi_chu="HSDT không có thỏa thuận liên danh — nhà thầu dự thầu độc lập")
    if not by_type.get(_GIA):
        return _verdict(KET_QUA_THIEU, bang_chung=f"HSDT không có: {_GIA}",
                        ghi_chu="thiếu bảng giá để đối chiếu tỷ lệ phân công")
    out = await vision_fn(SYS_RULE_LIEN_DANH,
                          lien_danh_prompt(pages_text(by_type[_TTLD]), pages_text(by_type[_GIA])),
                          validate=validate_phan_cong, max_tokens=_MAX_TOKENS)
    if out.status == "error":
        return _verdict(KET_QUA_LOI, bang_chung=f"AI lỗi: {out.error}", ghi_chu="cần soi lại")
    d = out.data
    ket_qua, bang_chung, ghi_chu = doi_chieu_phan_cong(d)
    them = d.get("ghi_chu", "")
    return _verdict(ket_qua, bang_chung=bang_chung,
                    trang=[int(t) for t in d.get("trang", []) if str(t).isdigit()],
                    ghi_chu=f"{ghi_chu}; {them}" if ghi_chu and them else (ghi_chu or them))


SKILL = RuleSkill(id="lien_danh_phan_cong_khop_bang_gia", ten=_TEN, ho_so_can=list(_HO_SO),
                  can_vendor=False, handler=handler, pham_vi=PHAM_VI_GOI)
