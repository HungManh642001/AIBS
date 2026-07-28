"""Luật: tài liệu HSDT nào GHI tên gói thầu thì tên đó phải TRÙNG gói thầu đang xét.

STANDING CHECK (pham_vi="goi", can_pkg=True): HSDT tái dùng từ gói khác (quên sửa tên gói) là lỗi
hợp lệ kinh điển mà HSMT không bao giờ nêu thành tiêu chí — phải kiểm thường trực. Verdict ra
`EvalResult.phat_hien_bo_sung`, chuyên gia tự quyết.

Rẻ + đúng phạm vi: code lọc TẤT ĐỊNH các dòng nhắc "gói thầu" trên MỌI loại hồ sơ (không nhắc ->
'đạt', 0 call LLM — điều kiện "nếu ghi tên gói thầu" nằm ở code). Có nhắc -> MỘT call LLM duy nhất
đối chiếu các dòng ứng viên với tên/mã gói đang xét (so tên gói cần hiểu viết tắt/OCR nhiễu —
fuzzy match tay dễ sai cả 2 chiều).
"""
from __future__ import annotations

from typing import Any

from services.prompts import cot_block

from experiment.evaluate.route import _norm
from experiment.evaluate.rules.registry import PHAM_VI_GOI, RuleSkill
from experiment.evaluate.schema import (
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_LOI, KET_QUA_SOI,
    PackageContext, PageRecord, VendorContext, Verdict, _Base,
)

_TEN = "Tên gói thầu ghi trong tài liệu khớp gói thầu đang xét"
_DOC_CAP = 1500       # trần dòng-ứng-viên MỖI loại hồ sơ trong prompt
_MAX_TOKENS = 4096
_KEY = "goi thau"     # đã _norm (thường + bỏ dấu)

SYS_RULE_TEN_GOI = (
    "Bạn là chuyên gia chấm thầu. Dưới đây là các dòng nhắc đến 'gói thầu' trích từ tài liệu HSDT "
    "theo từng loại hồ sơ. Đối chiếu TÊN GÓI THẦU ghi trong từng tài liệu với TÊN/MÃ GÓI THẦU ĐANG "
    "XÉT. ket_qua: 'đạt' nếu mọi tài liệu có ghi tên gói đều trùng gói đang xét (chấp nhận viết "
    "tắt/sai chính tả OCR nhẹ, cùng bản chất); 'không đạt' nếu có tài liệu ghi tên gói KHÁC; "
    "'cần làm rõ' nếu dòng trích không đủ để kết luận — TUYỆT ĐỐI KHÔNG bịa. Dòng chỉ nhắc chữ "
    "'gói thầu' mà KHÔNG ghi tên cụ thể thì KHÔNG tính là lệch. tai_lieu_lech: liệt kê tài liệu "
    "ghi tên khác kèm tên đã ghi + trang. bang_chung: trích nguyên văn dòng lệch (hoặc dòng khớp "
    "tiêu biểu). Chỉ trả JSON."
)


class TenGoiOut(_Base):
    ket_qua: str = KET_QUA_SOI
    tai_lieu_lech: list[dict[str, Any]] = []
    bang_chung: str = ""
    trang: list[int] = []
    do_tin: float = 0.0
    ghi_chu: str = ""


def validate_ten_goi(d: dict[str, Any]) -> dict[str, Any]:
    return TenGoiOut(**d).model_dump()


def extract_goi_thau_lines(pages: list[PageRecord]) -> str:
    """Dòng nhắc 'gói thầu' (so sau _norm — không dấu vẫn bắt) kèm số trang. Không có -> ''."""
    out: list[str] = []
    for p in pages:
        for line in p.text.splitlines():
            if _KEY in _norm(line):
                out.append(f"[Trang {p.trang}] {line.strip()}")
    return "\n".join(out)


def ten_goi_prompt(pkg: PackageContext, excerpts: dict[str, str]) -> str:
    docs = "\n\n".join(f"TÀI LIỆU {loai}:\n{text[:_DOC_CAP]}" for loai, text in excerpts.items())
    return (
        "[RULE:ten_goi_thau_khop]\n"
        f"GÓI THẦU ĐANG XÉT: {pkg.ten}" + (f" (mã: {pkg.ma_so})" if pkg.ma_so else "") + "\n\n"
        f"CÁC DÒNG NHẮC 'GÓI THẦU' TRONG HSDT (bóc từ ảnh):\n{docs}\n\n"
        + cot_block('{"ket_qua":"đạt|không đạt|cần làm rõ",'
                    '"tai_lieu_lech":[{"loai_ho_so":"...","ten_ghi":"...","trang":[...]}],'
                    '"bang_chung":"<trích dòng căn cứ>","trang":[1,3,...],"do_tin":0.0,"ghi_chu":""}')
    )


def _verdict(ket_qua: str, bang_chung: str = "", trang: list[int] | None = None,
             do_tin: float = 0.0, ghi_chu: str = "",
             nguon_doc: list[str] | None = None) -> Verdict:
    return Verdict(noi_dung_kiem_tra=_TEN, hsdt_kiem_tra="",
                   yeu_cau="Tài liệu HSDT ghi tên gói thầu phải trùng tên/mã gói thầu đang xét",
                   thong_tin_bo_sung="", ket_qua=ket_qua, bang_chung=bang_chung,
                   trang=trang or [], do_tin=do_tin, ghi_chu=ghi_chu, nguon_doc=nguon_doc or [])


async def handler(by_type: dict[str, list[PageRecord]], vendor_ctx: VendorContext | None,
                  criterion: dict[str, Any], vision_fn: Any,
                  *, nd: dict[str, Any] | None = None,
                  pkg: PackageContext | None = None) -> Verdict:
    # can_pkg=True: run_skill đã chặn pkg None; assert giữ hợp đồng nội bộ.
    assert pkg is not None
    excerpts = {loai: lines for loai, pages in by_type.items()
                if (lines := extract_goi_thau_lines(pages))}
    if not excerpts:
        return _verdict(KET_QUA_DAT, do_tin=1.0,
                        ghi_chu="không tài liệu nào ghi tên gói thầu — không có gì để đối chiếu")
    out = await vision_fn(SYS_RULE_TEN_GOI, ten_goi_prompt(pkg, excerpts),
                          validate=validate_ten_goi, max_tokens=_MAX_TOKENS)
    nguon = list(excerpts)
    if out.status == "error":
        return _verdict(KET_QUA_LOI, bang_chung=f"AI lỗi: {out.error}", ghi_chu="cần soi lại",
                        nguon_doc=nguon)
    d = out.data
    ket_qua = d.get("ket_qua", KET_QUA_SOI)
    if ket_qua not in {KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_SOI}:
        ket_qua = KET_QUA_SOI
    lech = "; ".join(f"{t.get('loai_ho_so', '?')}: ghi '{t.get('ten_ghi', '?')}'"
                     for t in d.get("tai_lieu_lech", []))
    bang_chung = d.get("bang_chung", "") or lech
    return _verdict(ket_qua, bang_chung=bang_chung,
                    trang=[int(t) for t in d.get("trang", []) if str(t).isdigit()],
                    do_tin=float(d.get("do_tin", 0.0) or 0.0), ghi_chu=d.get("ghi_chu", ""),
                    nguon_doc=nguon)


SKILL = RuleSkill(id="ten_goi_thau_khop", ten=_TEN, ho_so_can=[], can_vendor=False,
                  handler=handler, pham_vi=PHAM_VI_GOI, can_pkg=True)
