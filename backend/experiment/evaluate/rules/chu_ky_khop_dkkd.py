"""Luật: người ký đơn dự thầu KHỚP người đại diện pháp luật trong ĐKKD (tu_cach_phap_ly).

STANDING CHECK (pham_vi="goi"): chạy 1 lần/nhà thầu bất kể HSMT có nêu hay không — HSMT thường
chỉ ghi "đại diện hợp pháp ký" mà không nhắc ĐKKD, nếu chờ HSMT yêu cầu thì MẤT hẳn kiểm tra này.
Đổi lại, verdict KHÔNG gắn vào tiêu chí nào (gắn bừa vào tiêu chí đầu tiên có đơn dự thầu là quy
kết sai + phụ thuộc thứ tự), KHÔNG vào roll-up, KHÔNG tự kéo 'loại' — nó ra
`EvalResult.phat_hien_bo_sung` và hiện ở mục riêng "ngoài checklist HSMT" để chuyên gia tự quyết.

Text-only (chữ ký/dấu đã được ingest mô tả trong text). Quy ước: `trang` theo đơn dự thầu; trang
ĐKKD ghi trong bang_chung. Thiếu 1 trong 2 hồ sơ -> 'thiếu hồ sơ' (không gọi LLM).
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
_DOC_CAP = 3000       # trần text MỖI tài liệu trong prompt
_MAX_TOKENS = 4096

SYS_RULE_CHU_KY = (
    "Bạn là chuyên gia chấm thầu. Đối chiếu NGƯỜI KÝ trong ĐƠN DỰ THẦU với NGƯỜI ĐẠI DIỆN THEO "
    "PHÁP LUẬT trong hồ sơ tư cách pháp lý (ĐKKD). ket_qua: 'đạt' nếu cùng một người (hoặc ký theo "
    "ủy quyền hợp lệ nêu rõ trong hồ sơ); 'không đạt' nếu khác người và không có ủy quyền; "
    "'cần làm rõ' nếu KHÔNG tìm thấy tên một trong hai phía — TUYỆT ĐỐI KHÔNG bịa tên. "
    "bang_chung: trích cả hai phía kèm số trang từng tài liệu. Chỉ trả JSON."
)


class ChuKyOut(_Base):
    ket_qua: str = KET_QUA_SOI
    nguoi_ky: str = ""
    dai_dien_phap_luat: str = ""
    bang_chung: str = ""
    trang: list[int] = []
    do_tin: float = 0.0
    ghi_chu: str = ""


def validate_chu_ky(d: dict[str, Any]) -> dict[str, Any]:
    return ChuKyOut(**d).model_dump()


def chu_ky_prompt(don_text: str, dkkd_text: str) -> str:
    return (
        "[RULE:chu_ky_khop_dkkd]\n"
        f"ĐƠN DỰ THẦU (bóc từ ảnh):\n{don_text[:_DOC_CAP]}\n\n"
        f"HỒ SƠ TƯ CÁCH PHÁP LÝ / ĐKKD (bóc từ ảnh):\n{dkkd_text[:_DOC_CAP]}\n\n"
        + cot_block('{"ket_qua":"đạt|không đạt|cần làm rõ","nguoi_ky":"...","dai_dien_phap_luat":"...",'
                    '"bang_chung":"<trích 2 phía>","trang":[...],"do_tin":0.0,"ghi_chu":""}')
    )


def _verdict(ket_qua: str, bang_chung: str = "", trang: list[int] | None = None,
             do_tin: float = 0.0, ghi_chu: str = "") -> Verdict:
    return Verdict(noi_dung_kiem_tra=_TEN, hsdt_kiem_tra="don_du_thau",
                   yeu_cau="Người ký đơn dự thầu phải là đại diện pháp luật hoặc người được ủy quyền hợp lệ",
                   thong_tin_bo_sung="", ket_qua=ket_qua, bang_chung=bang_chung,
                   trang=trang or [], do_tin=do_tin, ghi_chu=ghi_chu, nguon_doc=list(_HO_SO))


async def handler(by_type: dict[str, list[PageRecord]], vendor_ctx: VendorContext | None,
                  criterion: dict[str, Any], vision_fn: Any,
                  *, nd: dict[str, Any] | None = None) -> Verdict:
    # standing check: không phục vụ nội dung nào -> bỏ qua nd.
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
    return _verdict(ket_qua, bang_chung=bang_chung,
                    trang=[int(t) for t in d.get("trang", []) if str(t).isdigit()],
                    do_tin=float(d.get("do_tin", 0.0) or 0.0), ghi_chu=d.get("ghi_chu", ""))


SKILL = RuleSkill(id="chu_ky_khop_dkkd", ten=_TEN, ho_so_can=list(_HO_SO), can_vendor=False,
                  handler=handler, pham_vi=PHAM_VI_GOI)
