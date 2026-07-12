"""Tóm tắt vai trò mỗi nguồn scan -> danh mục route cho decompose step-3.

AI sinh mặc định; người sửa tay file source_summaries.json thì bản sửa THẮNG (nạp ở
run_decompose._load_summaries). LLM lỗi -> fallback = mã nguồn (KHÔNG bịa nội dung).
"""
from __future__ import annotations

import logging
from typing import Any

from experiment.decompose.llm import LlmFn, default_llm_fn
from services.prompts import cot_block

log = logging.getLogger("experiment.multisource")

_TEXT_CAP = 8000  # ký tự tài liệu đưa vào prompt tóm tắt

SYS_SUMMARY = (
    "Bạn đọc TOÀN VĂN một tài liệu trong bộ hồ sơ mời thầu và TÓM TẮT 1-2 câu: tài liệu này là "
    "gì và CHỨA NHỮNG LOẠI THÔNG TIN NÀO (vd thời gian phát hành/đóng/mở thầu, giá gói thầu, "
    "chủ đầu tư, địa điểm...). Mục đích: giúp bước tra cứu chọn ĐÚNG tài liệu. Chỉ trả JSON."
)


def summary_prompt(source_doc: str, text: str) -> str:
    return (
        f"[TAG:SUMMARY:{source_doc}]\n"
        f"TÀI LIỆU (mã nguồn: {source_doc}):\n{text[:_TEXT_CAP]}\n\n"
        + cot_block('{"tom_tat":"<1-2 câu: tài liệu gì, chứa loại thông tin nào>"}')
    )


def validate_summary(d: dict[str, Any]) -> dict[str, Any]:
    return {"tom_tat": str(d.get("tom_tat", "") or "")}


async def summarize_source(source_doc: str, chunks: list[dict[str, Any]],
                           llm_fn: LlmFn | None = None) -> str:
    """chunks (đã OCR) của MỘT nguồn -> tóm tắt vai trò. Lỗi/rỗng -> mã nguồn (no-silent-mock)."""
    llm_fn = llm_fn or default_llm_fn
    text = "\n".join((c.get("text") or "") for c in chunks)
    out = await llm_fn(SYS_SUMMARY, summary_prompt(source_doc, text), validate=validate_summary)
    if out.status != "ok" or not out.data["tom_tat"].strip():
        log.warning("[summary] %s lỗi/rỗng (%s) -> dùng mã nguồn làm tóm tắt",
                    source_doc, getattr(out, "error", ""))
        return source_doc
    return out.data["tom_tat"].strip()
