"""Luật: người ký đơn dự thầu KHỚP người đại diện pháp luật trong ĐKKD (tu_cach_phap_ly).

STANDING CHECK (pham_vi="goi"): chạy 1 lần/nhà thầu bất kể HSMT có nêu hay không — HSMT thường
chỉ ghi "đại diện hợp pháp ký" mà không nhắc ĐKKD, nếu chờ HSMT yêu cầu thì MẤT hẳn kiểm tra này.
Đổi lại, verdict KHÔNG gắn vào tiêu chí nào (gắn bừa vào tiêu chí đầu tiên có đơn dự thầu là quy
kết sai + phụ thuộc thứ tự), KHÔNG vào roll-up, KHÔNG tự kéo 'loại' — nó ra
`EvalResult.phat_hien_bo_sung` và hiện ở mục riêng "ngoài checklist HSMT" để chuyên gia tự quyết.

Text-only (chữ ký/dấu đã được ingest mô tả trong text). Quy ước: `trang` theo đơn dự thầu; trang
ĐKKD ghi trong bang_chung. Thiếu 1 trong 2 hồ sơ -> 'thiếu hồ sơ' (không gọi LLM).

KÝ THAY (2 bước, rẽ nhánh ở CODE — không bắt LLM tự làm if/else): bước 1 đối chiếu người ký ↔ đại
diện PL; chỉ khi 'không đạt' mới xét giấy ủy quyền (giay_uy_quyen, file riêng trong HSDT):
- Không có GUQ -> 'không đạt' (ký thay không ủy quyền), KHÔNG gọi LLM lần 2.
- Có GUQ -> call 2 thẩm định 3 ý: người ủy quyền = đại diện PL; người được ủy quyền = người ký
  đơn; phạm vi ủy quyền bao gồm ký đơn dự thầu. Call 2 lỗi -> 'lỗi' (no-silent-mock).
"""
from __future__ import annotations

from typing import Any

from services.prompts import cot_block

from experiment.evaluate.route import pages_text
from experiment.evaluate.rules.registry import PHAM_VI_GOI, RuleSkill
from experiment.evaluate.schema import (
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_LOI, KET_QUA_SOI, KET_QUA_THIEU,
    PageRecord, VendorContext, Verdict, _Base,
)

_TEN = "Người ký đơn dự thầu khớp đại diện pháp luật (ĐKKD)"
_HO_SO = ["don_du_thau", "tu_cach_phap_ly"]
_GUQ = "giay_uy_quyen"        # hồ sơ TÙY CHỌN — chỉ xét khi người ký ≠ đại diện PL
_DOC_CAP = 3000       # trần text MỖI tài liệu trong prompt
_MAX_TOKENS = 4096

SYS_RULE_CHU_KY = (
    "Bạn là chuyên gia chấm thầu. Đối chiếu NGƯỜI KÝ trong ĐƠN DỰ THẦU với NGƯỜI ĐẠI DIỆN THEO "
    "PHÁP LUẬT trong hồ sơ tư cách pháp lý (ĐKKD). ket_qua: 'đạt' nếu cùng một người (hoặc ký theo "
    "ủy quyền hợp lệ nêu rõ trong hồ sơ); 'không đạt' nếu khác người và không có ủy quyền; "
    "'cần làm rõ' nếu KHÔNG tìm thấy tên một trong hai phía — TUYỆT ĐỐI KHÔNG bịa tên. "
    "bang_chung: trích cả hai phía kèm số trang từng tài liệu. Chỉ trả JSON."
)


SYS_RULE_UY_QUYEN = (
    "Bạn là chuyên gia chấm thầu. Người ký ĐƠN DỰ THẦU KHÔNG phải đại diện pháp luật — hãy thẩm "
    "định GIẤY ỦY QUYỀN theo ĐỦ 3 điều kiện: (1) người ủy quyền là ĐẠI DIỆN PHÁP LUẬT nêu dưới "
    "đây; (2) người được ủy quyền ĐÚNG là người đã ký đơn dự thầu; (3) nội dung/phạm vi ủy quyền "
    "bao gồm việc KÝ ĐƠN DỰ THẦU. ket_qua: 'đạt' khi thỏa CẢ BA; 'không đạt' khi vi phạm bất kỳ "
    "điều nào; 'cần làm rõ' khi thiếu thông tin — TUYỆT ĐỐI KHÔNG bịa tên hay phạm vi. "
    "bang_chung: trích nguyên văn giấy ủy quyền kèm số trang. Chỉ trả JSON."
)


class ChuKyOut(_Base):
    ket_qua: str = KET_QUA_SOI
    nguoi_ky: str = ""
    dai_dien_phap_luat: str = ""
    bang_chung: str = ""
    trang: list[int] = []
    do_tin: float = 0.0
    ghi_chu: str = ""


class UyQuyenOut(_Base):
    ket_qua: str = KET_QUA_SOI
    nguoi_uy_quyen: str = ""
    nguoi_duoc_uy_quyen: str = ""
    bang_chung: str = ""
    trang: list[int] = []
    do_tin: float = 0.0
    ghi_chu: str = ""


def validate_chu_ky(d: dict[str, Any]) -> dict[str, Any]:
    return ChuKyOut(**d).model_dump()


def validate_uy_quyen(d: dict[str, Any]) -> dict[str, Any]:
    return UyQuyenOut(**d).model_dump()


def chu_ky_prompt(don_text: str, dkkd_text: str) -> str:
    return (
        "[RULE:chu_ky_khop_dkkd]\n"
        f"ĐƠN DỰ THẦU (bóc từ ảnh):\n{don_text[:_DOC_CAP]}\n\n"
        f"HỒ SƠ TƯ CÁCH PHÁP LÝ / ĐKKD (bóc từ ảnh):\n{dkkd_text[:_DOC_CAP]}\n\n"
        + cot_block('{"ket_qua":"đạt|không đạt|cần làm rõ","nguoi_ky":"...","dai_dien_phap_luat":"...",'
                    '"bang_chung":"<trích 2 phía>","trang":[...],"do_tin":0.0,"ghi_chu":""}')
    )


def uy_quyen_prompt(guq_text: str, nguoi_ky: str, dai_dien: str) -> str:
    return (
        "[RULE:chu_ky_uy_quyen]\n"
        f"NGƯỜI KÝ ĐƠN DỰ THẦU: {nguoi_ky or '(không rõ)'}\n"
        f"ĐẠI DIỆN PHÁP LUẬT (theo ĐKKD): {dai_dien or '(không rõ)'}\n"
        f"GIẤY ỦY QUYỀN (bóc từ ảnh):\n{guq_text[:_DOC_CAP]}\n\n"
        + cot_block('{"ket_qua":"đạt|không đạt|cần làm rõ","nguoi_uy_quyen":"...",'
                    '"nguoi_duoc_uy_quyen":"...","bang_chung":"<trích GUQ>","trang":[...],'
                    '"do_tin":0.0,"ghi_chu":""}')
    )


def _verdict(ket_qua: str, bang_chung: str = "", trang: list[int] | None = None,
             do_tin: float = 0.0, ghi_chu: str = "",
             nguon_doc: list[str] | None = None) -> Verdict:
    return Verdict(noi_dung_kiem_tra=_TEN, hsdt_kiem_tra="don_du_thau",
                   yeu_cau="Người ký đơn dự thầu phải là đại diện pháp luật hoặc người được ủy quyền hợp lệ",
                   thong_tin_bo_sung="", ket_qua=ket_qua, bang_chung=bang_chung,
                   trang=trang or [], do_tin=do_tin, ghi_chu=ghi_chu,
                   nguon_doc=nguon_doc or list(_HO_SO))


async def handler(by_type: dict[str, list[PageRecord]], vendor_ctx: VendorContext | None,
                  criterion: dict[str, Any], vision_fn: Any,
                  *, nd: dict[str, Any] | None = None, pkg: Any = None) -> Verdict:
    # standing check: không phục vụ nội dung nào -> bỏ qua nd; không cần ngữ cảnh gói -> bỏ qua pkg.
    thieu = [c for c in _HO_SO if not by_type.get(c)]
    if thieu:
        return _verdict(KET_QUA_THIEU, bang_chung=f"HSDT không có: {', '.join(thieu)}",
                        ghi_chu="thiếu hồ sơ để đối chiếu chữ ký")
    out = await vision_fn(SYS_RULE_CHU_KY,
                          chu_ky_prompt(pages_text(by_type["don_du_thau"]),
                                        pages_text(by_type["tu_cach_phap_ly"])),
                          validate=validate_chu_ky, max_tokens=_MAX_TOKENS)
    if out.status == "error":
        return _verdict(KET_QUA_LOI, bang_chung=f"AI lỗi: {out.error}", ghi_chu="cần soi lại")
    d = out.data
    ket_qua = d.get("ket_qua", KET_QUA_SOI)
    if ket_qua not in {KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_SOI}:
        ket_qua = KET_QUA_SOI
    bang_chung = d.get("bang_chung", "") or \
        f"người ký: {d.get('nguoi_ky', '?')}; đại diện pháp luật: {d.get('dai_dien_phap_luat', '?')}"
    trang = [int(t) for t in d.get("trang", []) if str(t).isdigit()]
    if ket_qua == KET_QUA_KHONG:      # người ký ≠ đại diện PL -> xét ký thay theo ủy quyền
        return await _xet_uy_quyen(by_type, vision_fn, d, bang_chung, trang)
    return _verdict(ket_qua, bang_chung=bang_chung, trang=trang,
                    do_tin=float(d.get("do_tin", 0.0) or 0.0), ghi_chu=d.get("ghi_chu", ""))


async def _xet_uy_quyen(by_type: dict[str, list[PageRecord]], vision_fn: Any,
                        d1: dict[str, Any], bang_chung_1: str, trang_1: list[int]) -> Verdict:
    """Bước 2 (chỉ khi ký thay): thẩm định giấy ủy quyền — đúng người + đúng phạm vi ký đơn."""
    if not by_type.get(_GUQ):
        return _verdict(KET_QUA_KHONG, bang_chung=bang_chung_1, trang=trang_1,
                        do_tin=float(d1.get("do_tin", 0.0) or 0.0),
                        ghi_chu="người ký khác đại diện pháp luật và HSDT không có giấy ủy quyền")
    out = await vision_fn(SYS_RULE_UY_QUYEN,
                          uy_quyen_prompt(pages_text(by_type[_GUQ]),
                                          d1.get("nguoi_ky", ""), d1.get("dai_dien_phap_luat", "")),
                          validate=validate_uy_quyen, max_tokens=_MAX_TOKENS)
    nguon = _HO_SO + [_GUQ]
    if out.status == "error":
        return _verdict(KET_QUA_LOI, bang_chung=f"AI lỗi (thẩm định ủy quyền): {out.error}",
                        ghi_chu="cần soi lại", nguon_doc=nguon)
    d2 = out.data
    ket_qua = d2.get("ket_qua", KET_QUA_SOI)
    if ket_qua not in {KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_SOI}:
        ket_qua = KET_QUA_SOI
    bc2 = d2.get("bang_chung", "") or (f"người ủy quyền: {d2.get('nguoi_uy_quyen', '?')}; "
                                       f"người được ủy quyền: {d2.get('nguoi_duoc_uy_quyen', '?')}")
    return _verdict(ket_qua, bang_chung=f"{bang_chung_1}; ủy quyền: {bc2}", trang=trang_1,
                    do_tin=float(d2.get("do_tin", 0.0) or 0.0), ghi_chu=d2.get("ghi_chu", ""),
                    nguon_doc=nguon)


SKILL = RuleSkill(id="chu_ky_khop_dkkd", ten=_TEN, ho_so_can=list(_HO_SO), can_vendor=False,
                  handler=handler, pham_vi=PHAM_VI_GOI)
