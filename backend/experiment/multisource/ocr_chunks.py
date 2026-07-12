"""Cầu nối: OCR tài liệu mời thầu SCAN (vision) -> chunk dict tương thích chunks.jsonl.

Chunker HSMT chỉ chạy trên pdf-text; TBMT là scan nên đi đường riêng: render ảnh -> Qwen VL
bóc text -> cắt cửa sổ nhỏ -> chunk dict có source_doc. no-silent-mock: vision lỗi -> bỏ trang (log).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from experiment.evaluate.vision import default_vision_fn, pdf_to_images

log = logging.getLogger("experiment.multisource")

SYS_OCR = (
    "Bạn đọc ẢNH một trang tài liệu mời thầu (scan, tiếng Việt). (1) BÓC TOÀN BỘ chữ thành text, "
    "giữ chính xác số/ngày/giờ/đơn vị, KHÔNG bịa, KHÔNG tóm tắt; (2) gist: MỘT dòng liệt kê các "
    "LOẠI thông tin trang này chứa (vd 'thời điểm đóng/mở thầu, địa điểm, chủ đầu tư'). Chỉ trả JSON."
)

# nhãn người đọc cho section_path theo source_doc
_SECTION = {"tbmt": "Thông báo mời thầu"}


def ocr_prompt() -> str:
    return "[OCR] Trả JSON: {\"text\":\"<toàn bộ chữ trong ảnh>\",\"gist\":\"<1 dòng: các loại thông tin trang chứa>\"}"


def validate_ocr(d: dict[str, Any]) -> dict[str, Any]:
    return {"text": str(d.get("text", "") or ""), "gist": str(d.get("gist", "") or "")}


def _split_text(text: str, max_chars: int) -> list[str]:
    """Cắt text thành cửa sổ <= max_chars trên ranh giới dòng (giữ giá trị không bị chặt giữa chừng)."""
    text = (text or "").strip()
    if len(text) <= max_chars:
        return [text] if text else []
    out: list[str] = []
    buf = ""
    for line in text.splitlines():
        if buf and len(buf) + len(line) + 1 > max_chars:
            out.append(buf.strip())
            buf = ""
        buf = f"{buf}\n{line}" if buf else line
        while len(buf) > max_chars:  # 1 dòng dài hơn cửa sổ -> cắt cứng
            out.append(buf[:max_chars].strip())
            buf = buf[max_chars:]
    if buf.strip():
        out.append(buf.strip())
    return [p for p in out if p]


async def ocr_scan_to_chunks(pdf_path: str, source_doc: str, vision_fn: Any | None = None,
                             dpi: int = 200, max_chars: int = 600) -> list[dict[str, Any]]:
    """Scan PDF -> chunk dict per cửa sổ text. Tương thích index (chunk_to_node/keep_for_index)."""
    vision_fn = vision_fn or default_vision_fn
    section = _SECTION.get(source_doc, source_doc)
    images = pdf_to_images(Path(pdf_path).read_bytes(), dpi=dpi)
    log.info("[ocr] %s (%s): %d trang", Path(pdf_path).name, source_doc, len(images))
    chunks: list[dict[str, Any]] = []
    for page, png in enumerate(images, 1):
        out = await vision_fn(SYS_OCR, ocr_prompt(), images=[png], validate=validate_ocr)
        if out.status != "ok":
            log.warning("[ocr] %s tr%d lỗi vision: %s", source_doc, page, out.error)
            continue
        gist = str(out.data.get("gist", "") or "")  # 1 dòng/trang -> nuôi thẻ nguồn (summarize)
        for i, part in enumerate(_split_text(out.data.get("text", ""), max_chars)):
            chunks.append({
                "chunk_id": f"{source_doc}-p{page}-{i}", "text": part,
                "section_path": [section], "page_start": page, "page_end": page,
                "node_type": "text", "group_hint": "unknown",
                "source_doc": source_doc, "clause_id": "", "clause_doc": "",
                "doc": source_doc, "page_gist": gist,
            })
    return chunks
