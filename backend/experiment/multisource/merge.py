"""Gộp chunks HSMT (pdf-text) + chunks OCR (scan) thành 1 chunks.jsonl có source_doc."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Không thấy chunks: {p} (chạy chunking HSMT trước)")
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def merge_chunk_files(hsmt_jsonl: str, extra_chunks: list[dict[str, Any]], out_jsonl: str,
                      hsmt_source: str = "hsmt") -> int:
    """Ghi file gộp: chunk HSMT (gắn source_doc mặc định nếu thiếu) + extra_chunks (OCR). Trả tổng số."""
    merged = _read_jsonl(hsmt_jsonl)
    for c in merged:
        c.setdefault("source_doc", hsmt_source)
    merged.extend(extra_chunks)
    out = Path(out_jsonl)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in merged) + "\n", encoding="utf-8")
    return len(merged)
