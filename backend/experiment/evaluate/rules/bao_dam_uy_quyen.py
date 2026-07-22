"""Luật: người ký thư bảo lãnh dự thầu không phải người đứng đầu tổ chức phát hành -> cần GUQ.

STANDING CHECK (pham_vi="goi"): thư bảo lãnh do phó giám đốc/giám đốc chi nhánh ký mà không kèm
giấy ủy quyền hợp lệ là lỗi hợp lệ hay gặp; HSMT chỉ ghi "bảo đảm dự thầu hợp lệ" chứ không nêu
thành tiêu chí riêng. Verdict ra `EvalResult.phat_hien_bo_sung`, chuyên gia tự quyết.

MỘT call LLM (khác luật chu_ky_khop_dkkd 2 bước): điều kiện rẽ nhánh (chức danh người ký) và giấy
ủy quyền đều nằm TRONG CÙNG file scan bao_dam_du_thau — không có mốc tất định nào cho code rẽ
nhánh, tách 2 call chỉ tốn thêm mà không thêm bằng chứng. Thiếu hồ sơ -> 'thiếu hồ sơ' (0 call).
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

_TEN = "Người ký bảo đảm dự thầu có thẩm quyền (đứng đầu hoặc ủy quyền hợp lệ)"
_HO_SO = ["bao_dam_du_thau"]
_DOC_CAP = 6000       # cả thư bảo lãnh + GUQ scan chung 1 file -> trần rộng hơn luật 2-tài-liệu
_MAX_TOKENS = 4096

SYS_RULE_BAO_DAM = (
    "Bạn là chuyên gia chấm thầu. Đọc THƯ BẢO LÃNH DỰ THẦU (kèm mô tả chữ ký/con dấu đã bóc từ "
    "ảnh) và thẩm định THẨM QUYỀN người ký: (1) xác định NGƯỜI KÝ và CHỨC DANH; (2) nếu chức danh "
    "là người đứng đầu tổ chức phát hành (Tổng giám đốc, Giám đốc, Chủ tịch) -> 'đạt'; (3) nếu "
    "KHÁC (phó giám đốc, giám đốc/phó giám đốc chi nhánh, trưởng phòng...) -> BẮT BUỘC có GIẤY ỦY "
    "QUYỀN scan trong cùng tài liệu, và phải thỏa CẢ HAI: người được ủy quyền ĐÚNG là người ký; "
    "nội dung/phạm vi ủy quyền bao gồm việc KÝ thư bảo lãnh/bảo đảm dự thầu -> 'đạt', thiếu hoặc "
    "sai một trong hai -> 'không đạt'; không có giấy ủy quyền -> 'không đạt'. 'cần làm rõ' khi "
    "không đọc được người ký/chức danh — TUYỆT ĐỐI KHÔNG bịa tên, chức danh hay phạm vi ủy quyền. "
    "co_uy_quyen: tài liệu có kèm giấy ủy quyền không. bang_chung: trích nguyên văn (người ký, "
    "chức danh, câu ủy quyền nếu có) kèm số trang. Chỉ trả JSON."
)


class BaoDamOut(_Base):
    ket_qua: str = KET_QUA_SOI
    nguoi_ky: str = ""
    chuc_danh: str = ""
    co_uy_quyen: bool = False
    bang_chung: str = ""
    trang: list[int] = []
    do_tin: float = 0.0
    ghi_chu: str = ""


def validate_bao_dam(d: dict[str, Any]) -> dict[str, Any]:
    return BaoDamOut(**d).model_dump()


def bao_dam_prompt(bao_dam_text: str) -> str:
    return (
        "[RULE:chu_ky_bao_dam_uy_quyen]\n"
        f"BẢO ĐẢM DỰ THẦU (bóc từ ảnh, GUQ nếu có nằm cùng file):\n{bao_dam_text[:_DOC_CAP]}\n\n"
        + cot_block('{"ket_qua":"đạt|không đạt|cần làm rõ","nguoi_ky":"...","chuc_danh":"...",'
                    '"co_uy_quyen":false,"bang_chung":"<trích người ký/chức danh/câu ủy quyền>",'
                    '"trang":[...],"do_tin":0.0,"ghi_chu":""}')
    )


def _verdict(ket_qua: str, bang_chung: str = "", trang: list[int] | None = None,
             do_tin: float = 0.0, ghi_chu: str = "") -> Verdict:
    return Verdict(noi_dung_kiem_tra=_TEN, hsdt_kiem_tra="bao_dam_du_thau",
                   yeu_cau="Người ký bảo đảm dự thầu phải là người đứng đầu tổ chức phát hành "
                           "hoặc người được ủy quyền hợp lệ (GUQ đúng người, đúng phạm vi)",
                   thong_tin_bo_sung="", ket_qua=ket_qua, bang_chung=bang_chung,
                   trang=trang or [], do_tin=do_tin, ghi_chu=ghi_chu, nguon_doc=list(_HO_SO))


async def handler(by_type: dict[str, list[PageRecord]], vendor_ctx: VendorContext | None,
                  criterion: dict[str, Any], vision_fn: Any,
                  *, nd: dict[str, Any] | None = None, pkg: Any = None) -> Verdict:
    # standing check: không phục vụ nội dung nào -> bỏ qua nd; không cần ngữ cảnh gói -> bỏ qua pkg.
    if not by_type.get(_HO_SO[0]):
        return _verdict(KET_QUA_THIEU, bang_chung=f"HSDT không có: {_HO_SO[0]}",
                        ghi_chu="thiếu hồ sơ để thẩm định thẩm quyền người ký")
    out = await vision_fn(SYS_RULE_BAO_DAM, bao_dam_prompt(pages_text(by_type[_HO_SO[0]])),
                          validate=validate_bao_dam, max_tokens=_MAX_TOKENS)
    if out.status == "error":
        return _verdict(KET_QUA_LOI, bang_chung=f"AI lỗi: {out.error}", ghi_chu="cần soi lại")
    d = out.data
    ket_qua = d.get("ket_qua", KET_QUA_SOI)
    if ket_qua not in {KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_SOI}:
        ket_qua = KET_QUA_SOI
    bang_chung = d.get("bang_chung", "") or \
        f"người ký: {d.get('nguoi_ky', '?')}; chức danh: {d.get('chuc_danh', '?')}"
    return _verdict(ket_qua, bang_chung=bang_chung,
                    trang=[int(t) for t in d.get("trang", []) if str(t).isdigit()],
                    do_tin=float(d.get("do_tin", 0.0) or 0.0), ghi_chu=d.get("ghi_chu", ""))


SKILL = RuleSkill(id="chu_ky_bao_dam_uy_quyen", ten=_TEN, ho_so_can=list(_HO_SO),
                  can_vendor=False, handler=handler, pham_vi=PHAM_VI_GOI)
