# backend/experiment/chunking/chunker.py
"""Phát chunk lá: text theo ngân sách ký tự + overlap; bảng theo nhóm hàng lặp header.

E-BDL (Bảng dữ liệu) & E-CDNT (Chỉ dẫn nhà thầu) là bảng khoá-điều-khoản -> tách MỖI HÀNG 1 CHUNK
(1 điều khoản) kèm clause_id, để truy hồi theo mã chính xác (không gói nhiều điều khoản 1 chunk).
"""
from __future__ import annotations

import re

from .schema import Heading, Line, TableRegion, Chunk
from .headings import _norm
from .tree import iter_blocks_with_context

# Phát hiện 2 chương cần tách theo điều khoản, qua tiêu đề (bền hơn số chương).
_CLAUSE_DOCS = [("bang du lieu", "bdl"), ("chi dan nha thau", "cdnt")]
# Lấy mã điều khoản từ ô đầu hàng. E-BDL: "E-CDNT 18.2" / "E-CDNT 5.1 (c)"; E-CDNT: "4. Hành vi...".
_RE_BDL = re.compile(r"E-?CDNT\s+([\d.]+(?:\s*\([a-zđ]\))?)", re.I)
_RE_CDNT = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*\.")


def _clause_doc(stack: list[Heading]) -> str | None:
    """'bdl' | 'cdnt' nếu block thuộc chương Bảng dữ liệu / Chỉ dẫn nhà thầu; None nếu khác."""
    for h in stack:
        norm = _norm(h.title)
        for needle, label in _CLAUSE_DOCS:
            if needle in norm:
                return label
    return None


def _clause_id(cell0: str, clause_doc: str) -> str | None:
    """Trích mã điều khoản từ ô đầu hàng theo loại chương."""
    flat = " ".join((cell0 or "").split())
    m = _RE_BDL.search(flat) if clause_doc == "bdl" else _RE_CDNT.match(flat)
    if not m:
        return None
    return re.sub(r"\s+", "", m.group(1))

_GROUP_RULES = [
    ("hop le", "hop_le"),
    ("nang luc", "nang_luc"),
    ("kinh nghiem", "nang_luc"),
    ("ky thuat", "ky_thuat"),
    ("tai chinh", "tai_chinh"),
]


def group_hint(stack: list[Heading]) -> str:
    """Suy nhóm tiêu chí từ tiêu đề Mục đang chứa block."""
    muc = next((h for h in reversed(stack) if h.kind == "muc"), None)
    if muc is None:
        return "unknown"
    norm = _norm(muc.title)
    for needle, label in _GROUP_RULES:
        if needle in norm:
            return label
    return "unknown"


def split_text(text: str, max_chars: int = 1800, overlap: int = 180) -> list[tuple[str, int]]:
    """Cắt text thành cửa sổ <= max_chars, mỗi cửa sổ chồng `overlap` ký tự với cửa sổ trước."""
    text = text.strip()
    if len(text) <= max_chars:
        return [(text, 0)] if text else []
    parts: list[tuple[str, int]] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        parts.append((text[start:end], 0 if start == 0 else overlap))
        if end == len(text):
            break
        start = end - overlap
    return parts


def _chapter_no(stack: list[Heading]) -> str | None:
    ch = next((h for h in stack if h.kind == "chuong"), None)
    return ch.number if ch else None


def _muc_title(stack: list[Heading]) -> str | None:
    muc = next((h for h in reversed(stack) if h.kind == "muc"), None)
    return muc.title if muc else None


def _table_text(rows: list[list[str]]) -> str:
    return "\n".join(" | ".join(c for c in row) for row in rows)


def make_chunks(headings: list[Heading], body_lines: list[Line], tables: list[TableRegion],
                doc: str, max_chars: int = 1800, overlap: int = 180,
                table_rows_per_group: int = 12) -> list[Chunk]:
    """Sinh chunk theo thứ tự đọc; gộp các dòng text liên tiếp cùng section thành 1 đoạn."""
    blocks: list[Line | TableRegion] = [*body_lines, *tables]
    chunks: list[Chunk] = []
    counter = 0

    # Gom dòng text liên tiếp cùng stack thành buffer, flush khi gặp bảng / đổi section.
    buf_text: list[str] = []
    buf_stack: list[Heading] = []
    buf_pages: list[int] = []

    def _flush_text() -> None:
        nonlocal counter
        if not buf_text:
            return
        joined = "\n".join(buf_text)
        for part, ov in split_text(joined, max_chars, overlap):
            counter += 1
            chunks.append(_make(part, buf_stack, min(buf_pages), max(buf_pages),
                                "text", ov))
        buf_text.clear()
        buf_pages.clear()

    def _make(text, stack, p0, p1, node_type, overlap_prev,
              clause_id=None, clause_doc=None) -> Chunk:
        return Chunk(
            chunk_id=f"{doc}-{counter:04d}", doc=doc, text=text,
            section_path=[h.title for h in stack],
            chapter_no=_chapter_no(stack), section_title=_muc_title(stack),
            level=stack[-1].level if stack else 0,
            heading_number=stack[-1].number if stack else None,
            page_start=p0, page_end=p1, node_type=node_type,
            group_hint=group_hint(stack), char_len=len(text), overlap_prev=overlap_prev,
            clause_id=clause_id, clause_doc=clause_doc,
        )

    def _stack_key(s: list[Heading]) -> tuple:
        return tuple((h.kind, h.number, h.page) for h in s)

    for block, stack in iter_blocks_with_context(headings, blocks):
        if isinstance(block, TableRegion):
            _flush_text()
            rows = block.rows
            if not rows:
                continue
            # E-BDL / E-CDNT: mỗi HÀNG = 1 điều khoản -> 1 chunk riêng kèm clause_id.
            cdoc = _clause_doc(stack)
            if cdoc:
                for row in rows:
                    cid = _clause_id(row[0] if row else "", cdoc)
                    counter += 1
                    chunks.append(_make(_table_text([row]), stack, block.page, block.page,
                                        "clause", 0, clause_id=cid, clause_doc=cdoc))
                continue
            header = rows[0]
            body = rows[1:]
            if len(rows) <= table_rows_per_group:
                counter += 1
                chunks.append(_make(_table_text(rows), stack, block.page, block.page, "table", 0))
            else:
                for i in range(0, len(body), table_rows_per_group):
                    group = [header, *body[i:i + table_rows_per_group]]
                    counter += 1
                    chunks.append(_make(_table_text(group), stack, block.page, block.page,
                                        "table_row_group", 0))
        else:  # Line
            if buf_text and _stack_key(buf_stack) != _stack_key(stack):
                _flush_text()
            if not buf_text:
                buf_stack = stack
            buf_text.append(block.text)
            buf_pages.append(block.page)
    _flush_text()
    return chunks
