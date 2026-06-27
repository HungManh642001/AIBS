"""Trích layout (dòng + bảng) từ HSMT PDF-text bằng PyMuPDF."""
from __future__ import annotations

import re
from collections import Counter

import fitz

from .schema import Line, TableRegion

_BOLD_FLAG = 1 << 4          # bit 4 của span["flags"] = in đậm
_DIGITS = re.compile(r"\d+")
_TRANG = re.compile(r"^trang\s+\d+$", re.I)


def _mask(text: str) -> str:
    """Thay số bằng # để dòng furniture khác số trang vẫn gộp chung."""
    return _DIGITS.sub("#", text.strip())


def _strip_furniture(lines: list[Line], n_pages: int) -> list[Line]:
    """Bỏ header/footer lặp: text xuất hiện identically ở nhiều trang, hoặc 'Trang N'.

    Dùng exact text (không mask số) để tránh lọc nhầm nội dung thực có chứa số.
    Mask chỉ dùng để nhận dạng pattern có biến số (ví dụ mã tài liệu có trang trong text)
    nhưng trong thực tế header thường lặp nguyên văn, nên exact match đủ chính xác hơn.
    """
    seen_pages: dict[str, set[int]] = {}
    for l in lines:
        seen_pages.setdefault(l.text.strip(), set()).add(l.page)
    # Cũng track masked để bắt header dạng "Mã ABC - Trang 5" (biến số trang)
    masked_pages: dict[str, set[int]] = {}
    for l in lines:
        masked_pages.setdefault(_mask(l.text), set()).add(l.page)
    threshold = max(3, int(0.25 * n_pages))
    kept = []
    for l in lines:
        key = l.text.strip()
        if _TRANG.match(key):
            continue
        # Chỉ bỏ nếu exact text lặp nhiều trang (tránh false positive khi mask)
        if len(seen_pages[key]) >= threshold and len(key) <= 60:
            continue
        kept.append(l)
    return kept


def extract_lines(pdf_path: str) -> list[Line]:
    """Đọc mọi dòng văn bản, gộp span theo dòng, sắp theo thứ tự đọc, strip furniture."""
    doc = fitz.open(pdf_path)
    out: list[Line] = []
    for pno in range(doc.page_count):
        page_lines: list[Line] = []
        data = doc[pno].get_text("dict")
        for block in data["blocks"]:
            for ln in block.get("lines", []):
                spans = ln.get("spans", [])
                text = "".join(s["text"] for s in spans).strip()
                if not text:
                    continue
                bold = any(bool(s["flags"] & _BOLD_FLAG) for s in spans)
                size = max(s["size"] for s in spans)
                y0 = min(s["bbox"][1] for s in spans)
                x0 = min(s["bbox"][0] for s in spans)
                page_lines.append(Line(page=pno + 1, text=text, bold=bold,
                                       size=size, y0=y0, x0=x0))
        page_lines.sort(key=lambda l: (round(l.y0, 1), l.x0))
        out.extend(page_lines)
    n_pages = doc.page_count  # capture before close
    doc.close()
    return _strip_furniture(out, n_pages=n_pages or 1)


def extract_tables(pdf_path: str, lines: list[Line]) -> tuple[list[TableRegion], list[Line]]:
    """Phát hiện bảng bằng find_tables(); loại các dòng văn bản nằm trong bbox bảng."""
    doc = fitz.open(pdf_path)
    tables: list[TableRegion] = []
    spans_by_page: dict[int, list[tuple[float, float]]] = {}
    for pno in range(doc.page_count):
        try:
            found = doc[pno].find_tables()
        except Exception:
            continue
        for tbl in found.tables:
            x0, y0, x1, y1 = tbl.bbox
            rows = [[(c or "").strip() for c in row] for row in tbl.extract()]
            tables.append(TableRegion(page=pno + 1, y0=y0, y1=y1, rows=rows))
            spans_by_page.setdefault(pno + 1, []).append((y0, y1))
    doc.close()

    def _inside(l: Line) -> bool:
        for y0, y1 in spans_by_page.get(l.page, []):
            if y0 - 1 <= l.y0 <= y1 + 1:
                return True
        return False

    kept = [l for l in lines if not _inside(l)]
    return tables, kept
