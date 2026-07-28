from __future__ import annotations

from typing import Any

from experiment.decompose.llm import LlmFn, default_llm_fn
from services.prompts import cot_block

from experiment.logger_config import setup_logger
log = setup_logger('MULTISOURCE', 'multisource.log')

_TEXT_CAP = 8000

SYS_SUMMARY = (
    "Bạn nhận DANH SÁCH GIST (tóm tắt mỗi trang) hoặc TOÀN VĂN một tài liệu trong bộ hồ sơ mời thầu. "
    "Hãy trả về THẺ TÀI LIỆU: tom_tat (1-2 câu: tài liệu này là gì) + cac_truong (liệt kê ĐẦY ĐỦ "
    "các LOẠI thông tin tài liệu chứa, vd 'thời gian phát hành/đóng/mở thầu', 'giá gói thầu', "
    "'chủ đầu tư', 'địa điểm' ...). Mục đích: giúp bước tra cứu chọn ĐÚNG tài liệu. Không bịa loại " 
    "thông tin không có. Chỉ trả JSON"
)


def summary_prompt(source_doc: str, body: str) -> str:
    return (
        f"[TAG:SUMMARY:{source_doc}]\n"
        f"TÀI LIỆU (mã nguồn: {source_doc}):\n{body}\n\n"
        + cot_block('{"tom_tat":"<1-2 câu: tài liệu gì>", "cac_truong":["<loại thông tin>"]}')
    )


def validate_summary(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "tom_tat": str(d.get("tom_tat", "") or ""),
        "cac_truong": [s for s in ((str(t) or "").strip() for t in (d.get("cac_truong") or [])) if s],
    }


def _body_from_chunks(chunks: list[dict[str, Any]]) -> str:
    gists = [g for g in dict.fromkeys((c.get("page_gist") or "").strip() for c in chunks) if g]
    if gists:
        return "\n".join(f"-{g}" for g in gists)
    return "\n".join((c.get("text") or "") for c in chunks)[:_TEXT_CAP]


async def summarize_source(source_doc: str, chunks: list[dict[str, Any]],
                           llm_fn: LlmFn | None = None) -> dict[str, Any]:
    """chunks (đã OCR) của MỘT nguồn -> tóm tắt vai trò. Lỗi/rỗng -> mã nguồn (no-silent-mock)."""
    llm_fn = llm_fn or default_llm_fn

    out = await llm_fn(SYS_SUMMARY, summary_prompt(source_doc, _body_from_chunks(chunks)), validate=validate_summary)
    if out.status != "ok" or not out.data["tom_tat"].strip():
        log.warning(f"[summary] ({source_doc}) lỗi/rỗng ({getattr(out, 'error', '')}) -> thẻ fallback=mã nguồn")
        return {"tom_tat": source_doc, "cac_truong": []}
    return out.data