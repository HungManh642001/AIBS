"""Bảng neo gói thầu (hướng A): 1 call LLM/run trích mốc chung từ E-BDL + nguồn scan.

Mốc chung (đóng/mở thầu, hiệu lực E-HSDT...) là thứ chuẩn TƯƠNG ĐỐI tham chiếu tới
("≥120 ngày kể từ thời điểm đóng thầu" — mốc nằm ở TBMT, ngoài bằng chứng của lượt resolve).
Đính bảng neo vào mọi prompt RESOLVE để thong_tin_bo_sung TỰ ĐỦ. Lỗi/thiếu -> {} (hành vi
cũ giữ nguyên, KHÔNG bịa).
"""
from __future__ import annotations

import logging
from typing import Any

from experiment.decompose.llm import LlmFn
from experiment.decompose.prompts import SYS_ANCHORS, anchors_prompt
from experiment.decompose.schema import validate_anchors

log = logging.getLogger("experiment.decompose")

_BDL_CAP = 15000    # trần tư liệu E-BDL (đồng bộ workflow._BDL_CAP)
_SCAN_CAP = 12000   # trần 1 nguồn scan (đồng bộ workflow._SCAN_CAP)
_MAX_TOKENS = 8192  # Qwen3 có <think> -> budget rộng


async def build_anchors(llm_fn: LlmFn, bdl_rows: list[dict[str, Any]],
                        scan_texts: dict[str, str]) -> dict[str, dict[str, str]]:
    """Trích bảng neo {tên: {gia_tri, nguon}}; không tư liệu/lỗi -> {} (không bịa)."""
    parts: list[str] = []
    bdl = "\n".join(r.get("text", "") for r in bdl_rows).strip()
    if bdl:
        parts.append(f"[BẢNG DỮ LIỆU E-BDL]\n{bdl[:_BDL_CAP]}")
    for src, t in scan_texts.items():
        t = (t or "").strip()
        if t:
            parts.append(f"[{src.upper()}]\n{t[:_SCAN_CAP]}")
    if not parts:
        return {}
    out = await llm_fn(SYS_ANCHORS, anchors_prompt("\n\n".join(parts)),
                       validate=validate_anchors, max_tokens=_MAX_TOKENS)
    if out.status != "ok":
        log.warning("[anchors] lỗi trích bảng neo: %s (chạy tiếp KHÔNG neo)", out.error)
        return {}
    result: dict[str, dict[str, str]] = {}
    for a in out.data.get("neo", []):
        ten = (a.get("ten") or "").strip()
        gia_tri = (a.get("gia_tri") or "").strip()
        if ten and gia_tri:
            result[ten] = {"gia_tri": gia_tri, "nguon": (a.get("nguon") or "").strip()}
    return result
