"""B3 — luật: bảng giá của nhà thầu KHỚP giá trên webform (tài liệu dùng chung cả gói).

Webform chứa giá MỌI nhà thầu -> dò dòng đúng nhà thầu đang chấm TẤT ĐỊNH theo tên/MST/alias
(find_vendor_pages) rồi mới đối chiếu bằng LLM trên CHỈ các trang đã lọc (chống nhiễu + tràn
trần text). Không dò được dòng -> 'cần làm rõ' (no-fab, không gọi LLM).
"""
from __future__ import annotations

from experiment.evaluate.route import _norm
from experiment.evaluate.schema import PageRecord, VendorContext


def find_vendor_pages(webform_pages: list[PageRecord], ctx: VendorContext) -> list[PageRecord]:
    """Trang webform chứa nhà thầu đang chấm — match _norm substring theo tên/MST/aliases."""
    keys = [k for k in (_norm(ctx.ten), (ctx.ma_so_thue or "").strip(),
                        *(_norm(a) for a in ctx.aliases)) if k]
    out: list[PageRecord] = []
    for p in webform_pages:
        hay = _norm(p.text)
        if any(k in hay for k in keys):
            out.append(p)
    return out
