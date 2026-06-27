# HSMT Hierarchical Chunking — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Biến 1 file HSMT PDF-text thành cây cấu trúc (Phần→Chương→Mục→Điều) + danh sách chunk lá có truy vết section, để làm nền cho các bước embedding/RAG sau.

**Architecture:** Pipeline tuyến tính, không LLM/embedding. Trích layout bằng PyMuPDF `get_text("dict")` (font/bold/bbox) + `find_tables()`; phân loại heading bằng **bold + regex siết** (font-size vô dụng vì heading và body cùng 11pt); lọc mục lục bằng cụm-mật-độ + chuỗi-Chương-đơn-điệu; dựng cây bằng stack; phát chunk lá (text theo ngân sách ký tự + overlap, bảng theo nhóm hàng lặp header). Mỗi block thừa kế `section_path` của node sâu nhất đang mở.

**Tech Stack:** Python 3.11, PyMuPDF (`import fitz`) 1.24.7, pytest. Chỉ dùng thư viện đã có trong `backend/requirements.txt`.

## Global Constraints

- Chỉ xử lý **HSMT PDF-text**. KHÔNG làm nhánh scan/OCR (HSDT scan để bước sau).
- KHÔNG đụng `backend/services/` — toàn bộ code nằm trong `backend/experiment/chunking/`.
- Chuẩn hoá tiếng Việt: **luôn `.replace("đ","d")` TRƯỚC khi NFD** rồi mới bỏ dấu (đ/Đ không phải dấu tổ hợp).
- Tín hiệu heading = `bold (span["flags"] & 16)` **AND** regex; KHÔNG dùng ngưỡng font-size.
- Regex heading phải có ranh giới sau số/La Mã (`[.\:\-–]`) để không nuốt chữ thường ("Phần việc", "Chương V chỉ nhằm…").
- Response envelope `{"success","data","error"}` KHÔNG áp dụng ở đây (CLI/artefact, không phải API).
- File thầu thật trong `samples/` **không commit**; test chạm sample phải `pytest.skip` khi vắng file.
- Đơn vị kích thước chunk = **ký tự**. `MAX_CHARS = 1800`, `OVERLAP = 180`.
- Comment/chuỗi tiếng Việt, định danh code tiếng Anh (theo CLAUDE.md).

---

## File Structure

```
backend/experiment/
  __init__.py                      (Task 1)
  chunking/
    __init__.py                    (Task 1)
    schema.py                      (Task 1) dataclass: Line, TableRegion, Heading, OutlineNode, Chunk + serialize
    layout.py                      (Task 2,3) extract_lines(), extract_tables()
    headings.py                    (Task 4) _norm(), classify_heading()
    structure.py                   (Task 5) drop_toc_clusters(), keep_monotonic_chapters(), roman_to_int()
    tree.py                        (Task 6) build_outline(), iter_blocks_with_context()
    chunker.py                     (Task 7) group_hint(), split_text(), make_chunks()
    cli_chunk.py                   (Task 8) main(): pdf -> outline.json + chunks.jsonl + report.md
    tests/
      __init__.py                  (Task 1)
      conftest.py                  (Task 2) sample_pdf fixture (skip if absent)
      test_schema.py               (Task 1)
      test_layout_lines.py         (Task 2)
      test_layout_tables.py        (Task 3)
      test_headings.py             (Task 4)
      test_structure.py            (Task 5)
      test_tree.py                 (Task 6)
      test_chunker.py              (Task 7)
      test_end_to_end.py           (Task 8)
  samples/  (file thật, không commit)
  out/      (artefact, .gitignore)
```

Tất cả lệnh chạy từ `backend/`. Với các `__init__.py` này, pytest thêm `backend/` vào `sys.path`; import dùng `from experiment.chunking.schema import ...`.

---

### Task 1: Schema & package skeleton

**Files:**
- Create: `backend/experiment/__init__.py` (rỗng)
- Create: `backend/experiment/chunking/__init__.py` (rỗng)
- Create: `backend/experiment/chunking/tests/__init__.py` (rỗng)
- Create: `backend/experiment/chunking/schema.py`
- Test: `backend/experiment/chunking/tests/test_schema.py`

**Interfaces:**
- Produces: dataclasses `Line(page:int, text:str, bold:bool, size:float, y0:float, x0:float)`, `TableRegion(page:int, y0:float, y1:float, rows:list[list[str]])`, `Heading(kind:str, level:int, number:str, title:str, page:int, y0:float)`, `OutlineNode(level:int, kind:str, number:str, title:str, page_start:int, page_end:int, section_path:list[str], children:list[OutlineNode])`, `Chunk(...)`; constants `LEVEL_PHAN=0, LEVEL_CHUONG=1, LEVEL_MUC=2, LEVEL_DIEU=3`; helpers `chunks_to_jsonl(list[Chunk])->str`, `outline_to_json(list[OutlineNode])->str`.

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/chunking/tests/test_schema.py
import json
from experiment.chunking.schema import (
    Line, TableRegion, Heading, OutlineNode, Chunk,
    chunks_to_jsonl, outline_to_json,
    LEVEL_PHAN, LEVEL_CHUONG, LEVEL_MUC, LEVEL_DIEU,
)


def test_levels_are_ordered():
    assert (LEVEL_PHAN, LEVEL_CHUONG, LEVEL_MUC, LEVEL_DIEU) == (0, 1, 2, 3)


def test_chunks_to_jsonl_roundtrip_preserves_unicode():
    c = Chunk(
        chunk_id="c1", doc="hsmt", text="Tiêu chuẩn đánh giá",
        section_path=["Chương III. TIÊU CHUẨN"], chapter_no="III",
        section_title="Mục 1", level=LEVEL_MUC, heading_number="1",
        page_start=27, page_end=27, node_type="text",
        group_hint="hop_le", char_len=19, overlap_prev=0,
    )
    line = chunks_to_jsonl([c])
    parsed = json.loads(line)
    assert parsed["text"] == "Tiêu chuẩn đánh giá"
    assert parsed["group_hint"] == "hop_le"
    assert "\\u" not in line  # ensure_ascii=False giữ nguyên tiếng Việt


def test_outline_to_json_nests_children():
    child = OutlineNode(level=LEVEL_MUC, kind="muc", number="1", title="Mục 1",
                        page_start=27, page_end=39, section_path=["Chương III", "Mục 1"],
                        children=[])
    root = OutlineNode(level=LEVEL_CHUONG, kind="chuong", number="III", title="Chương III",
                       page_start=27, page_end=42, section_path=["Chương III"], children=[child])
    data = json.loads(outline_to_json([root]))
    assert data[0]["children"][0]["title"] == "Mục 1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest experiment/chunking/tests/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'experiment'`

- [ ] **Step 3: Create the package files and schema**

Create empty `backend/experiment/__init__.py`, `backend/experiment/chunking/__init__.py`, `backend/experiment/chunking/tests/__init__.py`.

```python
# backend/experiment/chunking/schema.py
"""Hợp đồng dữ liệu cho pipeline chunking phân cấp HSMT."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict

LEVEL_PHAN = 0
LEVEL_CHUONG = 1
LEVEL_MUC = 2
LEVEL_DIEU = 3


@dataclass
class Line:
    """Một dòng văn bản đã gộp span, kèm tín hiệu layout."""
    page: int      # 1-based
    text: str
    bold: bool
    size: float
    y0: float      # toạ độ đỉnh dòng (để sắp xếp đọc + gán section)
    x0: float


@dataclass
class TableRegion:
    """Một bảng do find_tables() phát hiện, kèm bbox dọc để lọc dòng trùng."""
    page: int
    y0: float
    y1: float
    rows: list[list[str]]


@dataclass
class Heading:
    kind: str      # phan | chuong | muc | dieu
    level: int
    number: str    # đã chuẩn hoá hoa, ví dụ "III", "2"
    title: str
    page: int
    y0: float


@dataclass
class OutlineNode:
    level: int
    kind: str
    number: str
    title: str
    page_start: int
    page_end: int
    section_path: list[str]
    children: list["OutlineNode"] = field(default_factory=list)


@dataclass
class Chunk:
    chunk_id: str
    doc: str
    text: str
    section_path: list[str]
    chapter_no: str | None
    section_title: str | None   # tiêu đề Mục đang chứa block
    level: int
    heading_number: str | None
    page_start: int
    page_end: int
    node_type: str              # text | table | table_row_group
    group_hint: str             # hop_le | nang_luc | ky_thuat | tai_chinh | unknown
    char_len: int
    overlap_prev: int


def chunks_to_jsonl(chunks: list[Chunk]) -> str:
    return "\n".join(json.dumps(asdict(c), ensure_ascii=False) for c in chunks)


def outline_to_json(nodes: list[OutlineNode]) -> str:
    return json.dumps([asdict(n) for n in nodes], ensure_ascii=False, indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest experiment/chunking/tests/test_schema.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/experiment/__init__.py backend/experiment/chunking/ \
        backend/experiment/chunking/tests/__init__.py
git commit -m "feat(experiment): chunking schema + package skeleton"
```

---

### Task 2: Layout line extraction + header/footer strip

**Files:**
- Create: `backend/experiment/chunking/layout.py`
- Create: `backend/experiment/chunking/tests/conftest.py`
- Test: `backend/experiment/chunking/tests/test_layout_lines.py`

**Interfaces:**
- Consumes: `Line` from `schema`.
- Produces: `extract_lines(pdf_path:str) -> list[Line]` (đã strip header/footer, sắp theo (page, y0, x0)); `_strip_furniture(lines:list[Line], n_pages:int) -> list[Line]` (tách riêng để test bằng chuỗi inline).

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/chunking/tests/test_layout_lines.py
from experiment.chunking.schema import Line
from experiment.chunking.layout import extract_lines, _strip_furniture


def _mk(page, text, y0=100.0):
    return Line(page=page, text=text, bold=False, size=11.0, y0=y0, x0=70.0)


def test_strip_removes_repeating_page_furniture():
    # "Trang N" và mã biểu lặp ở mọi trang -> rác, phải bỏ
    lines = []
    for p in range(1, 6):
        lines.append(_mk(p, "VSP-000-TM-238/BM-03", y0=20.0))
        lines.append(_mk(p, f"Trang {p + 28}", y0=820.0))
        lines.append(_mk(p, f"Nội dung thực trang {p}", y0=400.0))
    kept = _strip_furniture(lines, n_pages=5)
    texts = [l.text for l in kept]
    assert all("VSP-000-TM-238" not in t for t in texts)
    assert all(not t.startswith("Trang ") for t in texts)
    assert any("Nội dung thực" in t for t in texts)


def test_strip_keeps_unique_body_lines():
    lines = [_mk(1, "Chương III. TIÊU CHUẨN ĐÁNH GIÁ"), _mk(2, "Mục 1. Đánh giá tính hợp lệ")]
    kept = _strip_furniture(lines, n_pages=2)
    assert len(kept) == 2


def test_extract_lines_reads_chuong_iii_heading(sample_pdf):
    lines = extract_lines(sample_pdf)
    bold_texts = [l.text for l in lines if l.bold]
    assert any("TIÊU CHUẨN ĐÁNH GIÁ" in t for t in bold_texts)
    # heading Chương III thật nằm ~trang 27 (không phải mục lục trang 2-3)
    hits = [l.page for l in lines if "TIÊU CHUẨN ĐÁNH GIÁ E-HSDT" in l.text and l.bold]
    assert 27 in hits
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest experiment/chunking/tests/test_layout_lines.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'experiment.chunking.layout'` (test sample sẽ skip nếu vắng file).

- [ ] **Step 3: Create conftest fixture and layout.py**

```python
# backend/experiment/chunking/tests/conftest.py
from pathlib import Path

import pytest

_SAMPLE = (Path(__file__).resolve().parents[1].parent
           / "samples" / "E-HSMT gói thầu số VT-1954.25-KT-TTH.pdf")


@pytest.fixture
def sample_pdf():
    if not _SAMPLE.exists():
        pytest.skip("HSMT sample không có trong samples/ — bỏ qua test tích hợp")
    return str(_SAMPLE)
```

```python
# backend/experiment/chunking/layout.py
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
    """Bỏ header/footer lặp: text (đã mask số) xuất hiện ở nhiều trang, hoặc 'Trang N'."""
    seen_pages: dict[str, set[int]] = {}
    for l in lines:
        seen_pages.setdefault(_mask(l.text), set()).add(l.page)
    threshold = max(3, int(0.25 * n_pages))
    kept = []
    for l in lines:
        if _TRANG.match(l.text.strip()):
            continue
        if len(seen_pages[_mask(l.text)]) >= threshold and len(l.text.strip()) <= 60:
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
    doc.close()
    return _strip_furniture(out, n_pages=doc.page_count or 1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest experiment/chunking/tests/test_layout_lines.py -v`
Expected: PASS (2 passed, 1 passed or skipped tuỳ có sample).

- [ ] **Step 5: Commit**

```bash
git add backend/experiment/chunking/layout.py backend/experiment/chunking/tests/conftest.py \
        backend/experiment/chunking/tests/test_layout_lines.py
git commit -m "feat(experiment): layout line extraction + header/footer strip"
```

---

### Task 3: Table extraction + drop in-table lines

**Files:**
- Modify: `backend/experiment/chunking/layout.py` (thêm `extract_tables`)
- Test: `backend/experiment/chunking/tests/test_layout_tables.py`

**Interfaces:**
- Consumes: `Line`, `TableRegion`, `extract_lines`.
- Produces: `extract_tables(pdf_path:str, lines:list[Line]) -> tuple[list[TableRegion], list[Line]]` — trả về danh sách bảng và **danh sách dòng đã loại bỏ những dòng nằm trong bbox bảng** (tránh nhân đôi text bảng vào nhánh text).

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/chunking/tests/test_layout_tables.py
from experiment.chunking.layout import extract_lines, extract_tables


def test_bds_table_has_ecdnt_codes(sample_pdf):
    lines = extract_lines(sample_pdf)
    tables, _ = extract_tables(sample_pdf, lines)
    # Bảng BDS (Chương II ~ trang 23-26) là bảng 2 cột [mã E-CDNT, giá trị]
    bds = [t for t in tables if 23 <= t.page <= 26]
    assert bds, "phải phát hiện bảng BDS quanh trang 23-26"
    codes = [r[0] for t in bds for r in t.rows if r and r[0]]
    assert any("E-CDNT" in (c or "") for c in codes)


def test_lines_inside_table_are_dropped(sample_pdf):
    lines = extract_lines(sample_pdf)
    _, kept = extract_tables(sample_pdf, lines)
    assert len(kept) < len(lines)  # đã loại bớt dòng nằm trong bảng
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest experiment/chunking/tests/test_layout_tables.py -v`
Expected: FAIL — `ImportError: cannot import name 'extract_tables'` (hoặc skip nếu vắng sample).

- [ ] **Step 3: Add extract_tables to layout.py**

```python
# thêm vào cuối backend/experiment/chunking/layout.py

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest experiment/chunking/tests/test_layout_tables.py -v`
Expected: PASS (2 passed hoặc skipped nếu vắng sample).

- [ ] **Step 5: Commit**

```bash
git add backend/experiment/chunking/layout.py backend/experiment/chunking/tests/test_layout_tables.py
git commit -m "feat(experiment): table extraction + drop in-table lines"
```

---

### Task 4: Heading classification (bold + regex)

**Files:**
- Create: `backend/experiment/chunking/headings.py`
- Test: `backend/experiment/chunking/tests/test_headings.py`

**Interfaces:**
- Consumes: `Line`, `Heading`, level constants.
- Produces: `_norm(text:str)->str` (đ→d trước NFD); `classify_heading(line:Line) -> Heading | None`.

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/chunking/tests/test_headings.py
from experiment.chunking.schema import Line
from experiment.chunking.headings import classify_heading, _norm


def _line(text, bold=True):
    return Line(page=27, text=text, bold=bold, size=11.0, y0=100.0, x0=70.0)


def test_norm_handles_d_stroke_before_nfd():
    assert _norm("Đánh giá tính hợp lệ") == "danh gia tinh hop le"


def test_real_headings_classified():
    cases = {
        "Phần 1. THỦ TỤC ĐẤU THẦU": ("phan", 0, "1"),
        "Chương III. TIÊU CHUẨN ĐÁNH GIÁ E-HSDT": ("chuong", 1, "III"),
        "Mục 2. Tiêu chuẩn đánh giá về năng lực": ("muc", 2, "2"),
        "Chương II. BẢNG DỮ LIỆU ĐẤU THẦU": ("chuong", 1, "II"),
    }
    for text, (kind, level, num) in cases.items():
        h = classify_heading(_line(text))
        assert h is not None and (h.kind, h.level, h.number) == (kind, level, num)


def test_inline_references_not_headings():
    # 'Phần việc' (v là chữ La Mã), 'Chương V chỉ nhằm...' phải bị regex loại
    for text in ["Phần việc", "Chương V chỉ nhằm mục đích mô tả", "Chương III;"]:
        assert classify_heading(_line(text)) is None


def test_non_bold_cross_reference_not_heading():
    # 'Mục 18.5 E-CDNT' khớp regex nhưng KHÔNG bold -> loại nhờ cờ bold
    assert classify_heading(_line("Mục 18.5 E-CDNT thì", bold=False)) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest experiment/chunking/tests/test_headings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'experiment.chunking.headings'`

- [ ] **Step 3: Create headings.py**

```python
# backend/experiment/chunking/headings.py
"""Phân loại dòng heading bằng cờ bold + regex siết (font-size vô dụng ở HSMT này)."""
from __future__ import annotations

import re
import unicodedata

from .schema import Line, Heading, LEVEL_PHAN, LEVEL_CHUONG, LEVEL_MUC, LEVEL_DIEU


def _norm(text: str) -> str:
    lowered = text.lower().replace("đ", "d")
    nfkd = unicodedata.normalize("NFD", lowered)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


# Số/La Mã PHẢI theo sau bởi [.:-–] để không nuốt chữ thường ("phan viec", "chuong v chi...").
_PATTERNS = [
    ("phan", LEVEL_PHAN, re.compile(r"^phan\s+(\d{1,2}|[ivxlc]+)\s*[\.\:\-–]")),
    ("chuong", LEVEL_CHUONG, re.compile(r"^chuong\s+([ivxlc]+|\d{1,2})\s*[\.\:\-–]")),
    ("muc", LEVEL_MUC, re.compile(r"^muc\s+(\d{1,2})\s*[\.\:]")),
    ("dieu", LEVEL_DIEU, re.compile(r"^dieu\s+(\d{1,2})\s*[\.\:]")),
]


def classify_heading(line: Line) -> Heading | None:
    if not line.bold:
        return None
    norm = _norm(line.text.strip())
    for kind, level, rx in _PATTERNS:
        m = rx.match(norm)
        if m:
            return Heading(kind=kind, level=level, number=m.group(1).upper(),
                           title=line.text.strip(), page=line.page, y0=line.y0)
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest experiment/chunking/tests/test_headings.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/experiment/chunking/headings.py backend/experiment/chunking/tests/test_headings.py
git commit -m "feat(experiment): heading classification via bold + tightened regex"
```

---

### Task 5: Structure filtering (drop ToC + monotonic chapters)

**Files:**
- Create: `backend/experiment/chunking/structure.py`
- Test: `backend/experiment/chunking/tests/test_structure.py`

**Interfaces:**
- Consumes: `Heading`, level constants.
- Produces: `roman_to_int(s:str)->int`; `drop_toc_clusters(headings:list[Heading], min_cluster:int=4) -> list[Heading]`; `keep_monotonic_chapters(headings:list[Heading]) -> list[Heading]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/chunking/tests/test_structure.py
from experiment.chunking.schema import Heading, LEVEL_PHAN, LEVEL_CHUONG, LEVEL_MUC
from experiment.chunking.structure import roman_to_int, drop_toc_clusters, keep_monotonic_chapters


def _h(kind, level, number, page):
    return Heading(kind=kind, level=level, number=number, title=f"{kind} {number}",
                   page=page, y0=100.0)


def test_roman_to_int():
    assert [roman_to_int(x) for x in ("I", "II", "III", "IV", "V")] == [1, 2, 3, 4, 5]


def test_drop_toc_clusters_removes_dense_overview_page():
    toc = [_h("phan", LEVEL_PHAN, "1", 2), _h("chuong", LEVEL_CHUONG, "I", 2),
           _h("chuong", LEVEL_CHUONG, "II", 2), _h("chuong", LEVEL_CHUONG, "III", 2),
           _h("chuong", LEVEL_CHUONG, "IV", 2)]
    body = [_h("chuong", LEVEL_CHUONG, "I", 5), _h("muc", LEVEL_MUC, "1", 6)]
    kept = drop_toc_clusters(toc + body)
    assert all(h.page != 2 for h in kept)
    assert any(h.page == 5 for h in kept)


def test_keep_monotonic_chapters_drops_out_of_sequence():
    seq = [_h("chuong", LEVEL_CHUONG, "I", 5), _h("muc", LEVEL_MUC, "1", 6),
           _h("chuong", LEVEL_CHUONG, "III", 9),   # nhảy cóc -> loại (inline ref sót)
           _h("chuong", LEVEL_CHUONG, "II", 23),   # đúng thứ tự -> giữ
           _h("chuong", LEVEL_CHUONG, "III", 27)]
    kept = keep_monotonic_chapters(seq)
    chapters = [(h.number, h.page) for h in kept if h.kind == "chuong"]
    assert chapters == [("I", 5), ("II", 23), ("III", 27)]
    assert any(h.kind == "muc" for h in kept)  # Mục không bị đụng
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest experiment/chunking/tests/test_structure.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'experiment.chunking.structure'`

- [ ] **Step 3: Create structure.py**

```python
# backend/experiment/chunking/structure.py
"""Lọc nhiễu cấu trúc: bỏ cụm mục lục, giữ chuỗi Chương đơn điệu."""
from __future__ import annotations

from collections import defaultdict

from .schema import Heading

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman_to_int(s: str) -> int:
    total, prev = 0, 0
    for ch in reversed(s.upper()):
        v = _ROMAN.get(ch, 0)
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


def drop_toc_clusters(headings: list[Heading], min_cluster: int = 4) -> list[Heading]:
    """Trang nào có >= min_cluster heading cấp <=1 (Phần/Chương) là mục lục/overview -> bỏ cả trang."""
    by_page: dict[int, list[Heading]] = defaultdict(list)
    for h in headings:
        by_page[h.page].append(h)
    toc_pages = {p for p, hs in by_page.items()
                 if sum(1 for h in hs if h.level <= 1) >= min_cluster}
    return [h for h in headings if h.page not in toc_pages]


def _chapter_value(number: str) -> int:
    return roman_to_int(number) if number.isalpha() else int(number)


def keep_monotonic_chapters(headings: list[Heading]) -> list[Heading]:
    """Giữ Chương chỉ khi số tăng đúng +1 theo thứ tự đọc; loại Chương nhảy cóc (ref sót)."""
    out: list[Heading] = []
    last = 0
    for h in headings:
        if h.kind == "chuong":
            val = _chapter_value(h.number)
            if val == last + 1:
                last = val
                out.append(h)
            # else: bỏ — heading Chương lệch chuỗi
        else:
            out.append(h)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest experiment/chunking/tests/test_structure.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/experiment/chunking/structure.py backend/experiment/chunking/tests/test_structure.py
git commit -m "feat(experiment): drop ToC clusters + monotonic chapter filter"
```

---

### Task 6: Outline tree + block-context walk

**Files:**
- Create: `backend/experiment/chunking/tree.py`
- Test: `backend/experiment/chunking/tests/test_tree.py`

**Interfaces:**
- Consumes: `Heading`, `OutlineNode`, `Line`, `TableRegion`.
- Produces: `build_outline(headings:list[Heading]) -> list[OutlineNode]` (cây lồng nhau, có `page_end`); `iter_blocks_with_context(headings:list[Heading], blocks:list[Line|TableRegion]) -> Iterator[tuple[object, list[Heading]]]` — sinh từng block (Line hoặc TableRegion) kèm **stack heading đang mở** (sắp xếp toàn bộ theo (page, y0)).

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/chunking/tests/test_tree.py
from experiment.chunking.schema import (
    Heading, Line, TableRegion, LEVEL_CHUONG, LEVEL_MUC,
)
from experiment.chunking.tree import build_outline, iter_blocks_with_context


def _h(kind, level, number, page, y0=50.0):
    return Heading(kind=kind, level=level, number=number, title=f"{kind} {number}",
                   page=page, y0=y0)


def test_build_outline_nests_muc_under_chuong():
    headings = [_h("chuong", LEVEL_CHUONG, "III", 27),
                _h("muc", LEVEL_MUC, "1", 27, y0=80.0),
                _h("muc", LEVEL_MUC, "2", 28)]
    roots = build_outline(headings)
    assert len(roots) == 1
    assert [c.number for c in roots[0].children] == ["1", "2"]
    assert roots[0].section_path == ["chuong III"]
    assert roots[0].children[0].section_path == ["chuong III", "muc 1"]


def test_build_outline_sets_page_end_from_next_sibling():
    headings = [_h("chuong", LEVEL_CHUONG, "III", 27),
                _h("chuong", LEVEL_CHUONG, "IV", 43)]
    roots = build_outline(headings)
    assert roots[0].page_end == 42  # tới ngay trước Chương IV


def test_iter_blocks_with_context_attaches_deepest_stack():
    headings = [_h("chuong", LEVEL_CHUONG, "III", 27),
                _h("muc", LEVEL_MUC, "1", 27, y0=80.0)]
    body = Line(page=27, text="Giá dự thầu phải cố định", bold=False, size=11.0, y0=120.0, x0=70.0)
    tbl = TableRegion(page=28, y0=60.0, y1=300.0, rows=[["E-CDNT 1.1", "Tên Chủ đầu tư"]])
    results = list(iter_blocks_with_context(headings, [body, tbl]))
    assert len(results) == 2
    body_block, body_stack = results[0]
    assert [h.number for h in body_stack] == ["III", "1"]
    tbl_block, tbl_stack = results[1]
    assert isinstance(tbl_block, TableRegion)
    assert [h.number for h in tbl_stack] == ["III", "1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest experiment/chunking/tests/test_tree.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'experiment.chunking.tree'`

- [ ] **Step 3: Create tree.py**

```python
# backend/experiment/chunking/tree.py
"""Dựng cây outline + duyệt block kèm ngữ cảnh section (stack heading đang mở)."""
from __future__ import annotations

from typing import Iterator

from .schema import Heading, Line, TableRegion, OutlineNode


def _pos(obj) -> tuple[int, float]:
    return (obj.page, obj.y0)


def build_outline(headings: list[Heading]) -> list[OutlineNode]:
    """Stack-based: heading có level nhỏ hơn là cha. page_end suy từ heading kế cùng/cao cấp."""
    roots: list[OutlineNode] = []
    stack: list[OutlineNode] = []
    for h in sorted(headings, key=_pos):
        node = OutlineNode(level=h.level, kind=h.kind, number=h.number, title=h.title,
                           page_start=h.page, page_end=h.page, section_path=[], children=[])
        while stack and stack[-1].level >= h.level:
            stack.pop()
        if stack:
            node.section_path = stack[-1].section_path + [h.title]
            stack[-1].children.append(node)
        else:
            node.section_path = [h.title]
            roots.append(node)
        stack.append(node)

    # page_end: tới ngay trước heading kế tiếp có level <= của nó (theo thứ tự phẳng).
    flat = sorted(headings, key=_pos)
    for i, h in enumerate(flat):
        end = None
        for nxt in flat[i + 1:]:
            if nxt.level <= h.level:
                end = nxt.page - 1 if nxt.page > h.page else h.page
                break
        _set_page_end(roots, h, end)
    return roots


def _set_page_end(nodes: list[OutlineNode], h: Heading, end: int | None) -> None:
    for n in nodes:
        if n.page_start == h.page and n.title == h.title and n.kind == h.kind:
            if end is not None:
                n.page_end = end
            return
        _set_page_end(n.children, h, end)


def iter_blocks_with_context(
    headings: list[Heading], blocks: list[Line | TableRegion]
) -> Iterator[tuple[Line | TableRegion, list[Heading]]]:
    """Trộn heading + block theo (page, y0); với mỗi block, trả stack heading đang mở."""
    events: list[tuple[tuple[int, float], int, object]] = []
    for h in headings:
        events.append((_pos(h), 0, h))       # heading ưu tiên trước block cùng vị trí
    for b in blocks:
        events.append((_pos(b), 1, b))
    events.sort(key=lambda e: (e[0], e[1]))

    stack: list[Heading] = []
    for _, kind, obj in events:
        if kind == 0:
            while stack and stack[-1].level >= obj.level:
                stack.pop()
            stack.append(obj)
        else:
            yield obj, list(stack)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest experiment/chunking/tests/test_tree.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/experiment/chunking/tree.py backend/experiment/chunking/tests/test_tree.py
git commit -m "feat(experiment): outline tree + block-context walk"
```

---

### Task 7: Chunk emission (text budget + table row-groups)

**Files:**
- Create: `backend/experiment/chunking/chunker.py`
- Test: `backend/experiment/chunking/tests/test_chunker.py`

**Interfaces:**
- Consumes: `Line`, `TableRegion`, `Heading`, `Chunk`, `iter_blocks_with_context`, `_norm`.
- Produces: `group_hint(stack:list[Heading]) -> str`; `split_text(text:str, max_chars:int=1800, overlap:int=180) -> list[tuple[str,int]]`; `make_chunks(headings:list[Heading], body_lines:list[Line], tables:list[TableRegion], doc:str, max_chars:int=1800, overlap:int=180, table_rows_per_group:int=12) -> list[Chunk]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/chunking/tests/test_chunker.py
from experiment.chunking.schema import Heading, Line, TableRegion, LEVEL_CHUONG, LEVEL_MUC
from experiment.chunking.chunker import group_hint, split_text, make_chunks


def _h(kind, level, number, title, page, y0=50.0):
    return Heading(kind=kind, level=level, number=number, title=title, page=page, y0=y0)


def test_group_hint_maps_muc_titles():
    assert group_hint([_h("muc", LEVEL_MUC, "1", "Mục 1. Đánh giá tính hợp lệ", 27)]) == "hop_le"
    assert group_hint([_h("muc", LEVEL_MUC, "2", "Mục 2. năng lực và kinh nghiệm", 28)]) == "nang_luc"
    assert group_hint([_h("muc", LEVEL_MUC, "3", "Mục 3. về kỹ thuật", 40)]) == "ky_thuat"
    assert group_hint([_h("muc", LEVEL_MUC, "4", "Mục 4. về tài chính", 40)]) == "tai_chinh"
    assert group_hint([]) == "unknown"


def test_split_text_respects_budget_and_overlap():
    text = "x" * 4000
    parts = split_text(text, max_chars=1800, overlap=180)
    assert all(len(p) <= 1800 for p, _ in parts)
    assert parts[0][1] == 0 and parts[1][1] == 180  # overlap_prev


def test_make_chunks_text_section_carries_section_path():
    headings = [_h("chuong", LEVEL_CHUONG, "III", "Chương III. TIÊU CHUẨN", 27),
                _h("muc", LEVEL_MUC, "1", "Mục 1. Đánh giá tính hợp lệ", 27, y0=80.0)]
    body = [Line(page=27, text="Giá dự thầu phải cố định bằng số.", bold=False,
                 size=11.0, y0=120.0, x0=70.0)]
    chunks = make_chunks(headings, body, [], doc="hsmt")
    assert chunks and chunks[0].node_type == "text"
    assert chunks[0].chapter_no == "III"
    assert chunks[0].group_hint == "hop_le"
    assert chunks[0].section_path == ["Chương III. TIÊU CHUẨN", "Mục 1. Đánh giá tính hợp lệ"]


def test_make_chunks_large_table_splits_into_row_groups_with_header():
    headings = [_h("chuong", LEVEL_CHUONG, "II", "Chương II. BẢNG DỮ LIỆU", 23)]
    header = ["Mã", "Giá trị"]
    rows = [header] + [[f"E-CDNT {i}", f"giá trị {i}"] for i in range(30)]
    tbl = TableRegion(page=23, y0=60.0, y1=700.0, rows=rows)
    chunks = make_chunks(headings, [], [tbl], doc="hsmt", table_rows_per_group=12)
    groups = [c for c in chunks if c.node_type == "table_row_group"]
    assert len(groups) >= 2
    assert all("Mã" in c.text and "Giá trị" in c.text for c in groups)  # header lặp mỗi nhóm
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest experiment/chunking/tests/test_chunker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'experiment.chunking.chunker'`

- [ ] **Step 3: Create chunker.py**

```python
# backend/experiment/chunking/chunker.py
"""Phát chunk lá: text theo ngân sách ký tự + overlap; bảng theo nhóm hàng lặp header."""
from __future__ import annotations

from .schema import Heading, Line, TableRegion, Chunk
from .headings import _norm
from .tree import iter_blocks_with_context

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

    def _make(text, stack, p0, p1, node_type, overlap_prev) -> Chunk:
        return Chunk(
            chunk_id=f"{doc}-{counter:04d}", doc=doc, text=text,
            section_path=[h.title for h in stack],
            chapter_no=_chapter_no(stack), section_title=_muc_title(stack),
            level=stack[-1].level if stack else 0,
            heading_number=stack[-1].number if stack else None,
            page_start=p0, page_end=p1, node_type=node_type,
            group_hint=group_hint(stack), char_len=len(text), overlap_prev=overlap_prev,
        )

    def _stack_key(s: list[Heading]) -> tuple:
        return tuple((h.kind, h.number, h.page) for h in s)

    for block, stack in iter_blocks_with_context(headings, blocks):
        if isinstance(block, TableRegion):
            _flush_text()
            rows = block.rows
            if not rows:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest experiment/chunking/tests/test_chunker.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/experiment/chunking/chunker.py backend/experiment/chunking/tests/test_chunker.py
git commit -m "feat(experiment): chunk emission (text budget + table row-groups)"
```

---

### Task 8: CLI + end-to-end artefacts + golden metrics

**Files:**
- Create: `backend/experiment/chunking/cli_chunk.py`
- Create: `backend/experiment/.gitignore` (chứa `out/` và `samples/`)
- Test: `backend/experiment/chunking/tests/test_end_to_end.py`

**Interfaces:**
- Consumes: tất cả module trên.
- Produces: `run(pdf_path:str, out_dir:str) -> dict` (trả metrics dict: `n_chunks, n_chapters, groups_found, bds_table_pages, over_budget, coverage_ratio`); `main(argv=None)` (argparse: `--pdf`, `--out`).

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/chunking/tests/test_end_to_end.py
import json
from pathlib import Path

from experiment.chunking.cli_chunk import run


def test_end_to_end_on_real_hsmt(sample_pdf, tmp_path):
    metrics = run(sample_pdf, str(tmp_path))

    outline = json.loads((tmp_path / "outline.json").read_text(encoding="utf-8"))
    chunks = [json.loads(l) for l in (tmp_path / "chunks.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    assert (tmp_path / "report.md").exists()

    # 1) Chuỗi Chương I..V dựng đúng (đơn điệu, không dính mục lục)
    chapters = [n["number"] for n in outline if n["kind"] == "chuong"]
    assert chapters[:5] == ["I", "II", "III", "IV", "V"]

    # 2) Chương III có đủ 4 nhóm tiêu chí
    assert {"hop_le", "nang_luc", "ky_thuat", "tai_chinh"} <= set(metrics["groups_found"])

    # 3) Có chunk bảng BDS quanh trang 23-26
    assert any(c["node_type"].startswith("table") and 23 <= c["page_start"] <= 26
               for c in chunks)

    # 4) Không chunk text nào vượt ngân sách
    assert metrics["over_budget"] == 0

    # 5) Chunk có truy vết section
    assert all(c["section_path"] for c in chunks if c["node_type"] == "text")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest experiment/chunking/tests/test_end_to_end.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'experiment.chunking.cli_chunk'` (skip nếu vắng sample).

- [ ] **Step 3: Create cli_chunk.py and .gitignore**

```python
# backend/experiment/chunking/cli_chunk.py
"""CLI: HSMT PDF-text -> outline.json + chunks.jsonl + report.md (artefact soi tay)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .schema import chunks_to_jsonl, outline_to_json, MAX_CHARS  # noqa: F401  (MAX_CHARS optional)
from .layout import extract_lines, extract_tables
from .headings import classify_heading
from .structure import drop_toc_clusters, keep_monotonic_chapters
from .tree import build_outline
from .chunker import make_chunks

_MAX_CHARS = 1800


def run(pdf_path: str, out_dir: str) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    doc = Path(pdf_path).stem

    lines = extract_lines(pdf_path)
    tables, body_lines = extract_tables(pdf_path, lines)

    # Tách heading khỏi dòng body để không nhân đôi text heading vào chunk.
    headings = []
    non_heading: list = []
    for l in body_lines:
        h = classify_heading(l)
        if h is not None:
            headings.append(h)
        else:
            non_heading.append(l)
    headings = keep_monotonic_chapters(drop_toc_clusters(headings))

    outline = build_outline(headings)
    chunks = make_chunks(headings, non_heading, tables, doc=doc, max_chars=_MAX_CHARS)

    (out / "outline.json").write_text(outline_to_json(outline), encoding="utf-8")
    (out / "chunks.jsonl").write_text(chunks_to_jsonl(chunks), encoding="utf-8")

    groups_found = sorted({c.group_hint for c in chunks if c.group_hint != "unknown"})
    over_budget = sum(1 for c in chunks if c.node_type == "text" and c.char_len > _MAX_CHARS)
    bds_pages = sorted({c.page_start for c in chunks
                        if c.node_type.startswith("table") and 23 <= c.page_start <= 26})
    metrics = {
        "n_chunks": len(chunks),
        "n_chapters": sum(1 for n in outline if n["kind"] == "chuong") if False else
                      sum(1 for h in headings if h.kind == "chuong"),
        "groups_found": groups_found,
        "bds_table_pages": bds_pages,
        "over_budget": over_budget,
    }

    report = [
        f"# Báo cáo chunking — {doc}",
        "",
        f"- Tổng chunk: **{metrics['n_chunks']}**",
        f"- Số Chương dựng được: **{metrics['n_chapters']}**",
        f"- Nhóm tiêu chí tìm thấy: **{', '.join(groups_found) or 'không'}**",
        f"- Trang bảng BDS (23-26): **{bds_pages or 'không'}**",
        f"- Chunk text vượt {_MAX_CHARS} ký tự: **{over_budget}**",
        "",
        "## Outline (Chương / Mục)",
    ]
    for n in outline:
        if n["kind"] in ("chuong", "phan"):
            report.append(f"- {n['title']}  (tr {n['page_start']}–{n['page_end']})")
            for c in n.get("children", []):
                report.append(f"    - {c['title']}  (tr {c['page_start']}–{c['page_end']})")
    (out / "report.md").write_text("\n".join(report), encoding="utf-8")
    return metrics


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Chunk HSMT PDF-text phân cấp")
    ap.add_argument("--pdf", required=True, help="đường dẫn HSMT PDF-text")
    ap.add_argument("--out", default="experiment/out", help="thư mục artefact")
    args = ap.parse_args(argv)
    metrics = run(args.pdf, args.out)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

Sửa import thừa: `schema.py` không export `MAX_CHARS` — bỏ dòng `from .schema import ... MAX_CHARS`. Dùng đúng:

```python
from .schema import chunks_to_jsonl, outline_to_json
```

Và đơn giản hoá `n_chapters`:

```python
    metrics = {
        "n_chunks": len(chunks),
        "n_chapters": sum(1 for h in headings if h.kind == "chuong"),
        "groups_found": groups_found,
        "bds_table_pages": bds_pages,
        "over_budget": over_budget,
    }
```

`backend/experiment/.gitignore`:

```gitignore
out/
samples/
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest experiment/chunking/tests/test_end_to_end.py -v`
Expected: PASS (1 passed; hoặc skipped nếu vắng sample). Sau đó chạy CLI thật:

Run: `cd backend && python -m experiment.chunking.cli_chunk --pdf "experiment/samples/E-HSMT gói thầu số VT-1954.25-KT-TTH.pdf" --out experiment/out`
Expected: in JSON metrics; mở `experiment/out/report.md` soi cây Chương/Mục bằng mắt.

- [ ] **Step 5: Commit**

```bash
git add backend/experiment/chunking/cli_chunk.py backend/experiment/.gitignore \
        backend/experiment/chunking/tests/test_end_to_end.py
git commit -m "feat(experiment): chunking CLI + end-to-end golden metrics"
```

---

## Acceptance (nghiệm thu bước 1)

Chạy `python -m pytest experiment/chunking/tests -v` → tất cả pass (test sample skip nếu vắng file). Chạy CLI trên HSMT thật và soi `report.md`:

- [ ] Chuỗi Chương `I, II, III, IV, V` dựng đúng, không dính mục lục (trang 2–3, 7).
- [ ] Chương III có đủ 4 nhóm `hop_le, nang_luc, ky_thuat, tai_chinh`.
- [ ] Bảng BDS (trang 23–26) ra chunk `table`/`table_row_group` giữ mã `E-CDNT`.
- [ ] `over_budget == 0`.
- [ ] Mọi chunk text có `section_path` không rỗng.

Đạt hết → chốt bước 1, sang **Bước 2 (embedding + index)**.

## Self-review notes (đã rà)

- **Đ/NFD**: `_norm` replace `đ→d` trước NFD — đúng global constraint.
- **Bold**: dùng `flags & 16`, không dùng font-size — đúng dữ liệu thật.
- **Type consistency**: `make_chunks`, `iter_blocks_with_context`, `build_outline`, `classify_heading` chữ ký khớp giữa các task; `Chunk`/`OutlineNode` field dùng nhất quán ở Task 1/7/8.
- **import dư MAX_CHARS** trong cli_chunk đã ghi rõ phải bỏ ở Step 3.
- **YAGNI**: chưa làm Phần-level monotonic (không gate nghiệm thu); chưa làm Điều-level chunk riêng (Điều rơi vào text-section của Mục) — đủ cho mục tiêu định vị 4 nhóm + BDS.
