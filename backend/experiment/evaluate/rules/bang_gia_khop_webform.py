"""Luật: bảng giá của nhà thầu KHỚP giá trên webform (tài liệu dùng chung cả gói).

Webform chứa giá MỌI nhà thầu -> `find_vendor_pages` lọc về các TRANG có chứa nhà thầu đang chấm
rồi mới gọi LLM. GIỚI HẠN THẬT (đừng nói quá): lọc ở mức TRANG, không phải mức DÒNG — kết quả mở
thầu thật thường là bảng 1-2 trang chứa toàn bộ nhà thầu, khi đó phép lọc gần như không lọc gì và
việc chọn ĐÚNG DÒNG do LLM đảm nhiệm (SYS_RULE_BANG_GIA cảnh báo rõ + cấm lấy dòng nhà thầu khác).
KHÔNG lọc theo dòng vì OCR hay tách tên và giá thành 2 dòng -> lọc dòng sẽ âm thầm vứt mất giá.
Không dò được trang nào -> 'cần làm rõ' (no-fab, không gọi LLM).

Phạm vi tiêu chí: luật PHỤC VỤ nội dung route tới `bang_gia` trong tiêu chí khai đủ
[bang_gia, webform] -> verdict THAY THẾ kết luận của nội dung đó và mang danh tính của nó
(noi_dung_kiem_tra/yeu_cau/chuẩn/nguon_hsmt) để chuỗi audit không đứt.
"""
from __future__ import annotations

from typing import Any

from services.prompts import cot_block

from experiment.evaluate.route import find_vendor_pages, pages_text
from experiment.evaluate.rules.registry import RuleSkill
from experiment.evaluate.schema import (
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_LOI, KET_QUA_SOI, KET_QUA_THIEU,
    PageRecord, VendorContext, Verdict,
)
from experiment.evaluate.schema import validate_eval_verdict

_TEN = "Bảng giá khớp giá trên webform"
_HO_SO = ["bang_gia", "webform"]
_DOC_CAP = 3000       # trần text MỖI tài liệu trong prompt
_MAX_TOKENS = 4096

SYS_RULE_BANG_GIA = (
    "Bạn là chuyên gia chấm thầu. Đối chiếu GIÁ trong BẢNG CHÀO GIÁ của nhà thầu với GIÁ của "
    "CHÍNH nhà thầu đó trên WEBFORM (kết quả mở thầu). ket_qua: 'đạt' nếu giá khớp; 'không đạt' "
    "nếu lệch (nêu rõ 2 con số); 'cần làm rõ' nếu không đọc được giá một trong hai phía — "
    "TUYỆT ĐỐI KHÔNG bịa số. bang_chung: trích giá CẢ HAI phía kèm trang từng tài liệu.\n"
    "CẢNH BÁO: WEBFORM là bảng liệt kê NHIỀU nhà thầu. CHỈ đọc dòng của nhà thầu đang chấm (khớp "
    "tên/MST nêu ở đầu prompt). KHÔNG tìm thấy dòng của đúng nhà thầu đó -> trả 'cần làm rõ' và nói "
    "rõ là không thấy; TUYỆT ĐỐI KHÔNG lấy giá của nhà thầu khác hay dòng 'gần giống'. Chỉ trả JSON."
)


def bang_gia_prompt(bang_gia_text: str, webform_text: str, ctx: VendorContext,
                    nd: dict[str, Any] | None = None, yeu_cau_goc: str = "") -> str:
    mst = f" (MST {ctx.ma_so_thue})" if ctx.ma_so_thue else ""
    yeu_cau = (nd or {}).get("yeu_cau", "")
    goc = f"YÊU CẦU GỐC (nguyên văn HSMT): {yeu_cau_goc}\n" if yeu_cau_goc else ""
    hoi = f"YÊU CẦU (diễn giải — tham khảo): {yeu_cau}\n" if yeu_cau else ""
    return (
        "[RULE:bang_gia_khop_webform]\n"
        f"NHÀ THẦU ĐANG CHẤM: {ctx.ten}{mst}\n"
        f"{goc}{hoi}\n"
        f"BẢNG CHÀO GIÁ của nhà thầu (bóc từ ảnh):\n{bang_gia_text[:_DOC_CAP]}\n\n"
        f"WEBFORM — các trang chứa nhà thầu này (đã lọc):\n{webform_text[:_DOC_CAP]}\n\n"
        + cot_block('{"ket_qua":"đạt|không đạt|cần làm rõ","bang_chung":"<giá 2 phía + trang>",'
                    '"trang":[...],"do_tin":0.0,"ghi_chu":""}')
    )


def _verdict(ket_qua: str, bang_chung: str = "", trang: list[int] | None = None,
             do_tin: float = 0.0, ghi_chu: str = "", nd: dict[str, Any] | None = None) -> Verdict:
    """Verdict mang danh tính NỘI DUNG mà luật phục vụ (nd) — giữ chuỗi audit; nd=None -> nhãn luật."""
    n = nd or {}
    return Verdict(noi_dung_kiem_tra=n.get("noi_dung_kiem_tra") or _TEN,
                   hsdt_kiem_tra=n.get("hsdt_kiem_tra") or "bang_gia",
                   yeu_cau=(n.get("yeu_cau")
                            or "Giá bảng chào giá phải khớp giá nhà thầu công bố trên webform"),
                   thong_tin_bo_sung=n.get("thong_tin_bo_sung", ""), ket_qua=ket_qua,
                   bang_chung=bang_chung, trang=trang or [], do_tin=do_tin, ghi_chu=ghi_chu,
                   nguon_doc=list(_HO_SO), nguon_hsmt=n.get("nguon", ""))


async def handler(by_type: dict[str, list[PageRecord]], vendor_ctx: VendorContext | None,
                  criterion: dict[str, Any], vision_fn: Any,
                  *, nd: dict[str, Any] | None = None, pkg: Any = None) -> Verdict:
    # can_vendor=True: run_skill đã chặn ctx None; assert giữ hợp đồng nội bộ.
    assert vendor_ctx is not None
    thieu = [c for c in _HO_SO if not by_type.get(c)]
    if thieu:
        return _verdict(KET_QUA_THIEU, bang_chung=f"HSDT/gói không có: {', '.join(thieu)}",
                        ghi_chu="thiếu hồ sơ để đối chiếu giá", nd=nd)
    vendor_pages = find_vendor_pages(by_type["webform"], vendor_ctx)
    if not vendor_pages:
        return _verdict(KET_QUA_SOI, nd=nd,
                        ghi_chu=f"không dò được dòng nhà thầu '{vendor_ctx.ten}' trong webform")
    out = await vision_fn(SYS_RULE_BANG_GIA,
                          bang_gia_prompt(pages_text(by_type["bang_gia"]),
                                          pages_text(vendor_pages), vendor_ctx, nd,
                                          str(criterion.get("yeu_cau_goc", ""))),
                          validate=validate_eval_verdict, max_tokens=_MAX_TOKENS)
    if out.status == "error":
        return _verdict(KET_QUA_LOI, bang_chung=f"AI lỗi: {out.error}", ghi_chu="cần soi lại", nd=nd)
    d = out.data
    ket_qua = d.get("ket_qua", KET_QUA_SOI)
    if ket_qua not in {KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_SOI}:
        ket_qua = KET_QUA_SOI
    return _verdict(ket_qua, bang_chung=d.get("bang_chung", ""),
                    trang=[int(t) for t in d.get("trang", []) if str(t).isdigit()],
                    do_tin=float(d.get("do_tin", 0.0) or 0.0), ghi_chu=d.get("ghi_chu", ""), nd=nd)


SKILL = RuleSkill(id="bang_gia_khop_webform", ten=_TEN, ho_so_can=list(_HO_SO), can_vendor=True,
                  handler=handler)
