"""Tầng C+D — đánh giá từng nội dung (đối chiếu HSDT vs chuẩn HSMT) + roll-up tiêu chí."""
from __future__ import annotations

import logging
from typing import Any

from experiment.evaluate.prompts import SYS_EVAL, eval_prompt
from experiment.evaluate.route import has_visual_check, pages_text, route_pages
from experiment.evaluate.schema import (
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_LOI, KET_QUA_SOI, KET_QUA_THIEU,
    CriterionEval, PageRecord, Verdict, validate_eval_verdict,
)
from experiment.evaluate.vision import VisionFn

log = logging.getLogger("experiment.evaluate")
_KET_QUA_HOP_LE = {KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_SOI}
_EVAL_MAX_TOKENS = 4096


def _verdict(nd: dict[str, Any], ket_qua: str, bang_chung: str = "",
             trang: list[int] | None = None, do_tin: float = 0.0, ghi_chu: str = "") -> Verdict:
    return Verdict(
        noi_dung_kiem_tra=nd.get("noi_dung_kiem_tra", ""), hsdt_kiem_tra=nd.get("hsdt_kiem_tra", ""),
        yeu_cau=nd.get("yeu_cau", ""), thong_tin_bo_sung=nd.get("thong_tin_bo_sung", ""),
        ket_qua=ket_qua, bang_chung=bang_chung, trang=trang or [], do_tin=do_tin, ghi_chu=ghi_chu,
    )


async def eval_noi_dung(nd: dict[str, Any], pages: list[PageRecord], vision_fn: VisionFn) -> Verdict:
    """1 nội dung kiểm tra -> verdict (route + đối chiếu; đính ảnh nếu check thị giác)."""
    matched = route_pages(pages, nd.get("hsdt_kiem_tra", ""))
    if not matched:
        return _verdict(nd, KET_QUA_THIEU, bang_chung=f"HSDT không có: {nd.get('hsdt_kiem_tra', '')}",
                        ghi_chu="thiếu hồ sơ tương ứng")
    visual = has_visual_check(nd.get("kieu_check", ""))
    images = [p.image for p in matched if p.image] if visual else []
    out = await vision_fn(SYS_EVAL, eval_prompt(nd, pages_text(matched), has_image=bool(images)),
                          images=images, validate=validate_eval_verdict, max_tokens=_EVAL_MAX_TOKENS)
    if out.status == "error":
        return _verdict(nd, KET_QUA_LOI, bang_chung=f"AI lỗi: {out.error}", ghi_chu="cần soi lại")
    d = out.data
    ket_qua = d.get("ket_qua", KET_QUA_SOI)
    if ket_qua not in _KET_QUA_HOP_LE:
        ket_qua = KET_QUA_SOI
    return _verdict(nd, ket_qua, bang_chung=d.get("bang_chung", ""),
                    trang=[int(t) for t in d.get("trang", []) if str(t).isdigit()],
                    do_tin=float(d.get("do_tin", 0.0) or 0.0), ghi_chu=d.get("ghi_chu", ""))


async def evaluate_criterion(crit: dict[str, Any], pages: list[PageRecord],
                             vision_fn: VisionFn) -> CriterionEval:
    """Đánh giá mọi nội dung của 1 tiêu chí + roll-up. tien_quyet + không đạt -> loại."""
    ten = crit.get("ten", "")
    log.info("  [eval] %s", ten)
    verdicts: list[Verdict] = []
    for nd in crit.get("noi_dung_can_kiem_tra", []):
        verdicts.append(await eval_noi_dung(nd, pages, vision_fn))
    kq = {v.ket_qua for v in verdicts}
    if KET_QUA_KHONG in kq:
        ket_qua = KET_QUA_KHONG
    elif kq & {KET_QUA_SOI, KET_QUA_THIEU, KET_QUA_LOI}:
        ket_qua = KET_QUA_SOI
    elif verdicts and kq == {KET_QUA_DAT}:
        ket_qua = KET_QUA_DAT
    else:
        ket_qua = KET_QUA_SOI
    loai = ket_qua == KET_QUA_KHONG and bool(crit.get("tien_quyet"))
    return CriterionEval(nhom=crit.get("nhom", "hop_le"), ten=ten, tien_quyet=bool(crit.get("tien_quyet")),
                         ket_qua=ket_qua, loai=loai, verdicts=verdicts)
