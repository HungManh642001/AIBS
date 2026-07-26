"""Luật: người ký đơn dự thầu KHỚP người đại diện pháp luật trong ĐKKD (dang_ky_kinh_doanh).

STANDING CHECK (pham_vi="goi"): chạy 1 lần/nhà thầu bất kể HSMT có nêu hay không — HSMT thường
chỉ ghi "đại diện hợp pháp ký" mà không nhắc ĐKKD, nếu chờ HSMT yêu cầu thì MẤT hẳn kiểm tra này.
Đổi lại, verdict KHÔNG gắn vào tiêu chí nào (gắn bừa vào tiêu chí đầu tiên có đơn dự thầu là quy
kết sai + phụ thuộc thứ tự), KHÔNG vào roll-up, KHÔNG tự kéo 'loại' — nó ra
`EvalResult.phat_hien_bo_sung` và hiện ở mục riêng "ngoài checklist HSMT" để chuyên gia tự quyết.

Text-only (chữ ký/dấu đã được ingest mô tả trong text). Quy ước: `trang` theo đơn dự thầu; trang
ĐKKD ghi trong bang_chung. Thiếu ĐƠN DỰ THẦU -> 'thiếu hồ sơ' (không gọi LLM).

KÝ THAY (rẽ nhánh ở CODE — không bắt LLM tự làm if/else):
- ĐỦ đơn + ĐKKD: bước 1 đối chiếu người ký ↔ đại diện PL; chỉ khi 'không đạt' mới xét giấy ủy
  quyền (giay_uy_quyen, file riêng trong HSDT). Không có GUQ -> 'không đạt' (ký thay không ủy
  quyền), KHÔNG gọi LLM lần 2. Có GUQ -> call 2 thẩm định 3 ý: người ủy quyền = đại diện PL;
  người được ủy quyền = người ký đơn; phạm vi ủy quyền bao gồm ký đơn dự thầu.
- KHÔNG có ĐKKD (hay gặp trong thực tế): còn GUQ thì vẫn kiểm được phần lớn giá trị — MỘT call
  thẩm định 2 ý (người được ủy quyền = người ký đơn; phạm vi gồm ký đơn dự thầu), ghi_chu nêu rõ
  chưa đối chiếu được đại diện pháp luật. Không có cả GUQ -> 'thiếu hồ sơ' (không gọi LLM).

Bằng chứng ủy quyền LUÔN mở đầu bằng "ai ủy quyền cho ai" — chuyên gia cần thấy ngay cặp tên này
để rà lại, không phải đọc lần trong đoạn trích.
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
_DON = "don_du_thau"          # BẮT BUỘC — không có đơn thì không có chữ ký để đối chiếu
_DKKD = "dang_ky_kinh_doanh"
_HO_SO = [_DON, _DKKD]
_GUQ = "giay_uy_quyen"        # hồ sơ TÙY CHỌN — xét khi ký thay hoặc khi HSDT thiếu ĐKKD
_DOC_CAP = 3000       # trần text MỖI tài liệu trong prompt
_MAX_TOKENS = 4096

SYS_RULE_CHU_KY = (
    "Bạn là chuyên gia chấm thầu. Đối chiếu NGƯỜI KÝ trong ĐƠN DỰ THẦU với NGƯỜI ĐẠI DIỆN THEO "
    "PHÁP LUẬT trong GIẤY ĐĂNG KÝ KINH DOANH (ĐKKD). ket_qua: 'đạt' nếu cùng một người (hoặc ký theo "
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
    "BẮT BUỘC điền nguoi_uy_quyen và nguoi_duoc_uy_quyen (ai ủy quyền cho ai) để chuyên gia rà "
    "lại. bang_chung: trích nguyên văn giấy ủy quyền kèm số trang. Chỉ trả JSON."
)


SYS_RULE_UY_QUYEN_KHONG_DKKD = (
    "Bạn là chuyên gia chấm thầu. HSDT KHÔNG có giấy đăng ký kinh doanh (ĐKKD) nên KHÔNG đối chiếu "
    "được đại diện pháp luật — chỉ thẩm định GIẤY ỦY QUYỀN theo 2 điều kiện: (1) người được ủy "
    "quyền ĐÚNG là người đã ký ĐƠN DỰ THẦU dưới đây; (2) nội dung/phạm vi ủy quyền bao gồm việc "
    "KÝ ĐƠN DỰ THẦU. ket_qua: 'đạt' khi thỏa CẢ HAI; 'không đạt' khi vi phạm một trong hai; "
    "'cần làm rõ' khi không đọc được người ký đơn, người được ủy quyền hoặc phạm vi ủy quyền — "
    "TUYỆT ĐỐI KHÔNG bịa tên hay phạm vi, và KHÔNG suy đoán ai là đại diện pháp luật. BẮT BUỘC "
    "điền nguoi_uy_quyen và nguoi_duoc_uy_quyen (ai ủy quyền cho ai) để chuyên gia rà lại. "
    "bang_chung: trích nguyên văn giấy ủy quyền + câu ký trong đơn, kèm số trang. Chỉ trả JSON."
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
        f"GIẤY ĐĂNG KÝ KINH DOANH (ĐKKD, bóc từ ảnh):\n{dkkd_text[:_DOC_CAP]}\n\n"
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


_SCHEMA_UY_QUYEN = ('{"ket_qua":"đạt|không đạt|cần làm rõ","nguoi_uy_quyen":"...",'
                    '"nguoi_duoc_uy_quyen":"...","bang_chung":"<trích GUQ>","trang":[...],'
                    '"do_tin":0.0,"ghi_chu":""}')


def uy_quyen_khong_dkkd_prompt(don_text: str, guq_text: str) -> str:
    return (
        "[RULE:chu_ky_uy_quyen_khong_dkkd]\n"
        "LƯU Ý: HSDT KHÔNG có ĐKKD — chỉ xét người ký đơn ↔ người được ủy quyền và phạm vi.\n"
        f"ĐƠN DỰ THẦU (bóc từ ảnh):\n{don_text[:_DOC_CAP]}\n\n"
        f"GIẤY ỦY QUYỀN (bóc từ ảnh):\n{guq_text[:_DOC_CAP]}\n\n"
        + cot_block(_SCHEMA_UY_QUYEN)
    )


def _bang_chung_uy_quyen(d: dict[str, Any]) -> str:
    """Mở đầu bằng 'ai ủy quyền cho ai' rồi mới tới trích dẫn — chuyên gia đọc cặp tên ngay."""
    ai = (f"{d.get('nguoi_uy_quyen') or '?'} ủy quyền cho "
          f"{d.get('nguoi_duoc_uy_quyen') or '?'}")
    bc = d.get("bang_chung", "")
    return f"{ai}; {bc}" if bc else ai


def _ket_qua_hop_le(raw: str) -> str:
    return raw if raw in {KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_SOI} else KET_QUA_SOI


def _verdict(ket_qua: str, bang_chung: str = "", trang: list[int] | None = None,
             do_tin: float = 0.0, ghi_chu: str = "",
             nguon_doc: list[str] | None = None) -> Verdict:
    return Verdict(noi_dung_kiem_tra=_TEN, hsdt_kiem_tra=_DON,
                   yeu_cau="Người ký đơn dự thầu phải là đại diện pháp luật hoặc người được ủy quyền hợp lệ",
                   thong_tin_bo_sung="", ket_qua=ket_qua, bang_chung=bang_chung,
                   trang=trang or [], do_tin=do_tin, ghi_chu=ghi_chu,
                   nguon_doc=nguon_doc or list(_HO_SO))


async def handler(by_type: dict[str, list[PageRecord]], vendor_ctx: VendorContext | None,
                  criterion: dict[str, Any], vision_fn: Any,
                  *, nd: dict[str, Any] | None = None, pkg: Any = None) -> Verdict:
    # standing check: không phục vụ nội dung nào -> bỏ qua nd; không cần ngữ cảnh gói -> bỏ qua pkg.
    if not by_type.get(_DON):
        return _verdict(KET_QUA_THIEU, bang_chung=f"HSDT không có: {_DON}",
                        ghi_chu="thiếu hồ sơ để đối chiếu chữ ký")
    if not by_type.get(_DKKD):
        # Không có ĐKKD: còn giấy ủy quyền thì vẫn kiểm được người ký + phạm vi ủy quyền.
        if not by_type.get(_GUQ):
            return _verdict(KET_QUA_THIEU, bang_chung=f"HSDT không có: {_DKKD}",
                            ghi_chu="thiếu hồ sơ để đối chiếu chữ ký")
        return await _xet_uy_quyen_khong_dkkd(by_type, vision_fn)
    out = await vision_fn(SYS_RULE_CHU_KY,
                          chu_ky_prompt(pages_text(by_type[_DON]),
                                        pages_text(by_type[_DKKD])),
                          validate=validate_chu_ky, max_tokens=_MAX_TOKENS)
    if out.status == "error":
        return _verdict(KET_QUA_LOI, bang_chung=f"AI lỗi: {out.error}", ghi_chu="cần soi lại")
    d = out.data
    ket_qua = _ket_qua_hop_le(d.get("ket_qua", KET_QUA_SOI))
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
    return _verdict(_ket_qua_hop_le(d2.get("ket_qua", KET_QUA_SOI)),
                    bang_chung=f"{bang_chung_1}; ủy quyền: {_bang_chung_uy_quyen(d2)}",
                    trang=trang_1, do_tin=float(d2.get("do_tin", 0.0) or 0.0),
                    ghi_chu=d2.get("ghi_chu", ""), nguon_doc=nguon)


async def _xet_uy_quyen_khong_dkkd(by_type: dict[str, list[PageRecord]],
                                   vision_fn: Any) -> Verdict:
    """HSDT thiếu ĐKKD: thẩm định GUQ độc lập — người ký đơn = người được ủy quyền + đúng phạm vi.

    KHÔNG kết luận về đại diện pháp luật (không có căn cứ) — ghi_chu nêu rõ để chuyên gia biết
    verdict này hẹp hơn kiểm tra đầy đủ.
    """
    nguon = [_DON, _GUQ]
    out = await vision_fn(SYS_RULE_UY_QUYEN_KHONG_DKKD,
                          uy_quyen_khong_dkkd_prompt(pages_text(by_type[_DON]),
                                                     pages_text(by_type[_GUQ])),
                          validate=validate_uy_quyen, max_tokens=_MAX_TOKENS)
    if out.status == "error":
        return _verdict(KET_QUA_LOI, bang_chung=f"AI lỗi (thẩm định ủy quyền): {out.error}",
                        ghi_chu="cần soi lại", nguon_doc=nguon)
    d = out.data
    thieu_dkkd = ("HSDT không có ĐKKD — chỉ thẩm định giấy ủy quyền (người ký đơn + phạm vi), "
                  "CHƯA đối chiếu được đại diện pháp luật")
    ghi_chu = d.get("ghi_chu", "")
    return _verdict(_ket_qua_hop_le(d.get("ket_qua", KET_QUA_SOI)),
                    bang_chung=_bang_chung_uy_quyen(d),
                    trang=[int(t) for t in d.get("trang", []) if str(t).isdigit()],
                    do_tin=float(d.get("do_tin", 0.0) or 0.0),
                    ghi_chu=f"{thieu_dkkd}; {ghi_chu}" if ghi_chu else thieu_dkkd,
                    nguon_doc=nguon)


SKILL = RuleSkill(id="chu_ky_khop_dkkd", ten=_TEN, ho_so_can=list(_HO_SO), can_vendor=False,
                  handler=handler, pham_vi=PHAM_VI_GOI)
