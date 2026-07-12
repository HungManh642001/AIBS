"""Thẻ nguồn (tom_tat + cac_truong) cho mỗi nguồn scan -> danh mục route cho decompose step-3.

Build MAP-REDUCE: gist 1 dòng/trang (đi nhờ call OCR, xem ocr_chunks) -> gộp thành thẻ — nguồn dài
không bị cắt trần text. Chunk cũ không gist -> fallback nạp text thô (cắt _TEXT_CAP). AI sinh mặc
định; người sửa tay source_summaries.json thì bản sửa THẮNG (nạp ở run_decompose._load_summaries).
LLM lỗi -> thẻ fallback = mã nguồn (KHÔNG bịa nội dung).
"""
from __future__ import annotations

import logging
from typing import Any

from experiment.decompose.llm import LlmFn, default_llm_fn
from services.prompts import cot_block

log = logging.getLogger("experiment.multisource")

_TEXT_CAP = 8000  # trần ký tự khi fallback nạp text thô (không có gist)

SYS_SUMMARY = (
    "Bạn nhận DANH SÁCH GIST (mỗi dòng tóm 1 trang) hoặc TOÀN VĂN một tài liệu trong bộ hồ sơ mời "
    "thầu. Hãy trả THẺ TÀI LIỆU: tom_tat (1-2 câu: tài liệu này là gì) + cac_truong (liệt kê ĐẦY ĐỦ "
    "các LOẠI thông tin tài liệu chứa, vd 'thời điểm đóng/mở thầu', 'giá gói thầu', 'chủ đầu tư', "
    "'địa điểm'). Mục đích: giúp bước tra cứu chọn ĐÚNG tài liệu. KHÔNG bịa loại thông tin không có. "
    "Chỉ trả JSON."
)


def summary_prompt(source_doc: str, body: str) -> str:
    return (
        f"[TAG:SUMMARY:{source_doc}]\n"
        f"TÀI LIỆU (mã nguồn: {source_doc}):\n{body}\n\n"
        + cot_block('{"tom_tat":"<1-2 câu: tài liệu gì>","cac_truong":["<loại thông tin>"]}')
    )


def validate_summary(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "tom_tat": str(d.get("tom_tat", "") or ""),
        "cac_truong": [s for s in ((str(t) or "").strip() for t in (d.get("cac_truong") or [])) if s],
    }


def _body_from_chunks(chunks: list[dict[str, Any]]) -> str:
    """Ưu tiên gist từng trang (khử trùng, giữ thứ tự — không giới hạn số trang);
    không có gist -> text thô cắt trần."""
    gists = [g for g in dict.fromkeys((c.get("page_gist") or "").strip() for c in chunks) if g]
    if gists:
        return "\n".join(f"- {g}" for g in gists)
    return "\n".join((c.get("text") or "") for c in chunks)[:_TEXT_CAP]


async def summarize_source(source_doc: str, chunks: list[dict[str, Any]],
                           llm_fn: LlmFn | None = None) -> dict[str, Any]:
    """chunks (đã OCR) của MỘT nguồn -> thẻ {tom_tat, cac_truong}. Lỗi/rỗng -> thẻ mã nguồn."""
    llm_fn = llm_fn or default_llm_fn
    out = await llm_fn(SYS_SUMMARY, summary_prompt(source_doc, _body_from_chunks(chunks)),
                       validate=validate_summary)
    if out.status != "ok" or not out.data["tom_tat"].strip():
        log.warning("[summary] %s lỗi/rỗng (%s) -> thẻ fallback = mã nguồn",
                    source_doc, getattr(out, "error", ""))
        return {"tom_tat": source_doc, "cac_truong": []}
    return out.data
