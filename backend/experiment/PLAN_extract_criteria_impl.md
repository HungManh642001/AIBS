# Trích nội dung tiêu chuẩn 4 nhóm (Chương III) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Từ HSMT PDF-text, định vị Chương III và trích **nội dung** 4 nhóm tiêu chuẩn chính (Mục 1–4) thành `chuong3_groups.json` + `.md` cho người đọc/đối chiếu — KHÔNG phân rã tiêu chí, KHÔNG chấm, KHÔNG LLM.

**Architecture:** Pipeline xác định hoàn toàn, **tái dùng (import) thư viện chunking** đã nghiệm thu (`experiment.chunking.{layout,headings,structure,tree}`) để lấy nội dung *có cấu trúc* (text + bảng giữ nguyên `rows`). Gom block theo từng Mục, map Mục→nhóm theo số Mục (1–4) + từ khóa tiêu đề, đánh dấu Mục dạng tham chiếu (chưa lần theo). Render JSON + Markdown.

**Tech Stack:** Python 3.11, PyMuPDF (qua chunking lib), pytest. Không thêm dependency mới. Không gọi LLM.

## Global Constraints

- **Phạm vi**: CHỈ trích NỘI DUNG 4 nhóm chính (Mục 1–4) trong Chương III. KHÔNG phân rã thành tiêu chí, KHÔNG chấm, **KHÔNG gọi LLM**.
- Code CHỈ nằm trong `backend/experiment/extract/`. Được **import read-only** `backend/experiment/chunking/*`; **KHÔNG sửa** chunking hay `backend/services/`.
- **Giữ nguyên `rows` bảng** (verbatim) — không parse thành tiêu chí (việc đó ở bước phân rã sau).
- Chuẩn hóa tiếng Việt: **tái dùng** `experiment.chunking.headings._norm` (đ→d trước NFD) — KHÔNG tự viết lại.
- Chỉ giữ Mục có số ∈ {1,2,3,4}; bỏ Mục 5/6/7.
- JSON xuất với `ensure_ascii=False`.
- Định danh tiếng Anh, comment/chuỗi tiếng Việt.
- File mẫu hiện là `backend/experiment/samples/E-HSMT.pdf`; fixture test dùng **glob `samples/*.pdf`** và `pytest.skip` khi vắng.
- Chạy test từ `backend/`: `python -m pytest <đường dẫn cụ thể>` (đường dẫn tường minh override `testpaths = tests`).

---

## File Structure

```
backend/experiment/extract/
  __init__.py                 (T1) rỗng
  schema.py                   (T1) Block, GroupContent, groups_to_json
  refs.py                     (T1) detect_reference(text) -> (bool, dict|None)
  sections.py                 (T2) build_chuong3_groups(pdf) -> (chuong3_page, list[GroupContent])
  render.py                   (T3) groups_to_markdown(doc, chuong3_page, groups) -> str
  cli_extract.py              (T4) run(pdf, out_dir) -> dict ; main(argv)
  tests/
    __init__.py               (T1) rỗng
    conftest.py               (T2) sample_pdf fixture = glob samples/*.pdf
    test_schema.py            (T1)
    test_refs.py              (T1)
    test_sections.py          (T2) sample-gated
    test_render.py            (T3) inline
    test_end_to_end.py        (T4) sample-gated
```

Chạy từ `backend/`; package `experiment` đã có `__init__.py`. Import: `from experiment.extract.schema import ...`, `from experiment.chunking.layout import ...`.

---

### Task 1: Schema + reference detection

**Files:**
- Create: `backend/experiment/extract/__init__.py` (rỗng), `backend/experiment/extract/tests/__init__.py` (rỗng)
- Create: `backend/experiment/extract/schema.py`
- Create: `backend/experiment/extract/refs.py`
- Test: `backend/experiment/extract/tests/test_schema.py`, `backend/experiment/extract/tests/test_refs.py`

**Interfaces:**
- Produces: `Block(type:str, page:list[int], text:str|None=None, rows:list[list[str]]|None=None)`; `GroupContent(group:str, muc:str, muc_page:list[int], is_reference:bool, ref_target:dict|None, blocks:list[Block])`; `groups_to_json(doc:str, chuong3_page:list[int], groups:list[GroupContent])->str`; `detect_reference(text:str)->tuple[bool, dict|None]`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/experiment/extract/tests/test_schema.py
import json
from experiment.extract.schema import Block, GroupContent, groups_to_json


def test_groups_to_json_preserves_unicode_and_rows():
    g = GroupContent(
        group="nang_luc", muc="Mục 2. Tiêu chuẩn đánh giá về năng lực và kinh nghiệm",
        muc_page=[27, 40], is_reference=False, ref_target=None,
        blocks=[Block(type="table", page=[28, 39], rows=[["TT", "Mô tả"], ["1", "Lịch sử"]])],
    )
    s = groups_to_json("E-HSMT", [27, 42], [g])
    data = json.loads(s)
    assert "\\u" not in s
    assert data["doc"] == "E-HSMT"
    assert data["chuong3_page"] == [27, 42]
    assert data["groups"][0]["blocks"][0]["rows"][1] == ["1", "Lịch sử"]
    assert data["groups"][0]["blocks"][0]["text"] is None
```

```python
# backend/experiment/extract/tests/test_refs.py
from experiment.extract.refs import detect_reference


def test_detects_phan_reference():
    is_ref, target = detect_reference("Theo tài liệu đính kèm tại Phần 4. CÁC PHỤ LỤC")
    assert is_ref is True
    assert target == {"kind": "phan", "number": "4"}


def test_detects_chuong_reference_roman():
    is_ref, target = detect_reference("Đánh giá theo quy định tại Chương V của E-HSMT")
    assert is_ref is True
    assert target == {"kind": "chuong", "number": "V"}


def test_long_inline_content_is_not_reference():
    text = ("Nhà thầu phải đáp ứng đầy đủ các yêu cầu kỹ thuật sau đây. " * 12)
    is_ref, target = detect_reference(text)
    assert is_ref is False
    assert target is None


def test_empty_is_not_reference():
    assert detect_reference("") == (False, None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest experiment/extract/tests/test_schema.py experiment/extract/tests/test_refs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'experiment.extract'`

- [ ] **Step 3: Create the package files, schema.py and refs.py**

Create empty `backend/experiment/extract/__init__.py` and `backend/experiment/extract/tests/__init__.py`.

```python
# backend/experiment/extract/schema.py
"""Hợp đồng dữ liệu cho bước trích nội dung tiêu chuẩn 4 nhóm (Chương III)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict


@dataclass
class Block:
    """Một khối nội dung trong một Mục: text (đoạn văn) hoặc table (giữ nguyên rows gốc)."""
    type: str                       # "text" | "table"
    page: list[int]                 # [trang_đầu, trang_cuối]
    text: str | None = None         # cho type="text"
    rows: list[list[str]] | None = None  # cho type="table" — verbatim, KHÔNG parse


@dataclass
class GroupContent:
    group: str                      # hop_le | nang_luc | ky_thuat | tai_chinh
    muc: str                        # tiêu đề Mục
    muc_page: list[int]             # [trang_đầu, trang_cuối]
    is_reference: bool              # Mục chỉ là con trỏ sang section khác?
    ref_target: dict | None         # {"kind": "phan"|"chuong"|"muc", "number": "4"} nếu là tham chiếu
    blocks: list[Block] = field(default_factory=list)


def groups_to_json(doc: str, chuong3_page: list[int], groups: list[GroupContent]) -> str:
    return json.dumps(
        {"doc": doc, "chuong3_page": chuong3_page, "groups": [asdict(g) for g in groups]},
        ensure_ascii=False, indent=2,
    )
```

```python
# backend/experiment/extract/refs.py
"""Nhận diện Mục dạng 'con trỏ' (tham chiếu sang Phần/Chương/Mục khác). CHƯA lần theo."""
from __future__ import annotations

import re

from experiment.chunking.headings import _norm

# "theo ... (tại) (phan|chuong|muc) <số/La Mã>"  — chạy trên text đã bỏ dấu.
_REF_RE = re.compile(r"theo\b.*?\b(phan|chuong|muc)\s+(\d{1,2}|[ivxlc]+)\b")
_MAX_REF_LEN = 300  # con trỏ là Mục ngắn; text dài coi như nội dung inline


def detect_reference(text: str) -> tuple[bool, dict | None]:
    """Trả (is_reference, ref_target). True khi Mục ngắn và chứa cụm dẫn 'theo … Phần/Chương/Mục X'."""
    stripped = (text or "").strip()
    if not stripped or len(stripped) > _MAX_REF_LEN:
        return (False, None)
    m = _REF_RE.search(_norm(stripped))
    if not m:
        return (False, None)
    return (True, {"kind": m.group(1), "number": m.group(2).upper()})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest experiment/extract/tests/test_schema.py experiment/extract/tests/test_refs.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/experiment/extract/__init__.py backend/experiment/extract/schema.py \
        backend/experiment/extract/refs.py backend/experiment/extract/tests/__init__.py \
        backend/experiment/extract/tests/test_schema.py backend/experiment/extract/tests/test_refs.py
git commit -m "feat(experiment): extract schema + reference detection"
```

---

### Task 2: Per-Mục content gathering (sections.py)

**Files:**
- Create: `backend/experiment/extract/sections.py`
- Create: `backend/experiment/extract/tests/conftest.py`
- Test: `backend/experiment/extract/tests/test_sections.py`

**Interfaces:**
- Consumes: `Block`, `GroupContent` (schema); `detect_reference` (refs); from chunking: `extract_lines`, `extract_tables` (layout), `classify_heading`, `_norm` (headings), `drop_toc_clusters`, `keep_monotonic_chapters` (structure), `build_outline`, `iter_blocks_with_context` (tree); `Line`, `TableRegion` (chunking.schema).
- Produces: `build_chuong3_groups(pdf_path:str) -> tuple[list[int], list[GroupContent]]` — `([page_start, page_end], groups)`; groups chỉ gồm Mục 1–4, theo thứ tự hop_le, nang_luc, ky_thuat, tai_chinh.

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/extract/tests/test_sections.py
from experiment.extract.sections import build_chuong3_groups


def test_four_main_groups_extracted(sample_pdf):
    page, groups = build_chuong3_groups(sample_pdf)
    labels = [g.group for g in groups]
    assert labels == ["hop_le", "nang_luc", "ky_thuat", "tai_chinh"]
    assert page[0] == 27  # Chương III bắt đầu trang 27


def test_nang_luc_keeps_table_rows(sample_pdf):
    _, groups = build_chuong3_groups(sample_pdf)
    nl = next(g for g in groups if g.group == "nang_luc")
    tables = [b for b in nl.blocks if b.type == "table"]
    assert tables, "nhóm năng lực phải có ít nhất 1 block bảng"
    # giữ nguyên rows: có hàng dữ liệu mở đầu bằng TT '1'
    all_rows = [r for t in tables for r in (t.rows or [])]
    assert any(r and r[0].strip() == "1" for r in all_rows)


def test_ky_thuat_is_reference_to_phan_4(sample_pdf):
    _, groups = build_chuong3_groups(sample_pdf)
    kt = next(g for g in groups if g.group == "ky_thuat")
    assert kt.is_reference is True
    assert kt.ref_target == {"kind": "phan", "number": "4"}


def test_hop_le_and_tai_chinh_have_text(sample_pdf):
    _, groups = build_chuong3_groups(sample_pdf)
    hl = next(g for g in groups if g.group == "hop_le")
    tc = next(g for g in groups if g.group == "tai_chinh")
    hl_text = " ".join(b.text or "" for b in hl.blocks)
    tc_text = " ".join(b.text or "" for b in tc.blocks)
    assert "hợp lệ" in hl_text
    assert "thấp nhất" in tc_text  # phương pháp giá thấp nhất
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest experiment/extract/tests/test_sections.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'experiment.extract.sections'` (sample tests skip nếu vắng file).

- [ ] **Step 3: Create conftest.py and sections.py**

```python
# backend/experiment/extract/tests/conftest.py
import glob
from pathlib import Path

import pytest

_SAMPLES_DIR = Path(__file__).resolve().parents[1].parent / "samples"


@pytest.fixture
def sample_pdf():
    hits = sorted(glob.glob(str(_SAMPLES_DIR / "*.pdf")))
    if not hits:
        pytest.skip("Không có HSMT mẫu trong samples/ — bỏ qua test tích hợp")
    return hits[0]
```

```python
# backend/experiment/extract/sections.py
"""Định vị Chương III và gom NỘI DUNG 4 nhóm (Mục 1–4). Tái dùng thư viện chunking."""
from __future__ import annotations

from experiment.chunking.layout import extract_lines, extract_tables
from experiment.chunking.headings import classify_heading, _norm
from experiment.chunking.structure import drop_toc_clusters, keep_monotonic_chapters
from experiment.chunking.tree import build_outline, iter_blocks_with_context
from experiment.chunking.schema import Line, TableRegion, OutlineNode

from .schema import Block, GroupContent
from .refs import detect_reference

# Map số Mục -> nhóm (thứ tự chuẩn theo Thông tư). Dùng làm fallback nếu từ khóa không khớp.
_DEFAULT_BY_NUM = {1: "hop_le", 2: "nang_luc", 3: "ky_thuat", 4: "tai_chinh"}
_KEYWORD_RULES = [
    ("hop le", "hop_le"), ("nang luc", "nang_luc"), ("kinh nghiem", "nang_luc"),
    ("ky thuat", "ky_thuat"), ("tai chinh", "tai_chinh"),
]
_ORDER = ["hop_le", "nang_luc", "ky_thuat", "tai_chinh"]


def _muc_group(title: str, num: int) -> str:
    norm = _norm(title)
    for needle, label in _KEYWORD_RULES:
        if needle in norm:
            return label
    return _DEFAULT_BY_NUM[num]


def _find_chuong(nodes: list[OutlineNode], number: str) -> OutlineNode | None:
    for n in nodes:
        if n.kind == "chuong" and n.number == number:
            return n
        found = _find_chuong(n.children, number)
        if found is not None:
            return found
    return None


def _consolidate(items: list) -> list[Block]:
    """Gộp các dòng text liên tiếp thành 1 Block text; mỗi bảng thành 1 Block table (rows verbatim)."""
    out: list[Block] = []
    buf: list[str] = []
    buf_pages: list[int] = []

    def flush() -> None:
        if buf:
            out.append(Block(type="text", page=[min(buf_pages), max(buf_pages)],
                             text="\n".join(buf)))
            buf.clear()
            buf_pages.clear()

    for b in items:
        if isinstance(b, TableRegion):
            flush()
            out.append(Block(type="table", page=[b.page, b.page], rows=b.rows))
        elif isinstance(b, Line):
            buf.append(b.text)
            buf_pages.append(b.page)
    flush()
    return out


def build_chuong3_groups(pdf_path: str) -> tuple[list[int], list[GroupContent]]:
    lines = extract_lines(pdf_path)
    tables, body_lines = extract_tables(pdf_path, lines)

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
    ch3 = _find_chuong(outline, "III")
    if ch3 is None:
        return [0, 0], []
    chuong3_page = [ch3.page_start, ch3.page_end]

    # Gom block theo Mục, chỉ trong Chương III.
    blocks: list = [*non_heading, *tables]
    per_muc: dict[str, dict] = {}
    for block, stack in iter_blocks_with_context(headings, blocks):
        chuong = next((h for h in stack if h.kind == "chuong"), None)
        if chuong is None or chuong.number != "III":
            continue
        muc = next((h for h in reversed(stack) if h.kind == "muc"), None)
        if muc is None:
            continue
        per_muc.setdefault(muc.title, {"muc": muc, "items": []})["items"].append(block)

    groups: list[GroupContent] = []
    for title, info in per_muc.items():
        muc = info["muc"]
        try:
            num = int(muc.number)
        except ValueError:
            continue
        if num not in _DEFAULT_BY_NUM:   # bỏ Mục 5/6/7
            continue
        out_blocks = _consolidate(info["items"])
        full_text = " ".join(b.text for b in out_blocks if b.type == "text")
        is_ref, target = detect_reference(full_text)
        p1 = max([muc.page] + [b.page[1] for b in out_blocks]) if out_blocks else muc.page
        groups.append(GroupContent(
            group=_muc_group(title, num), muc=title, muc_page=[muc.page, p1],
            is_reference=is_ref, ref_target=target, blocks=out_blocks,
        ))

    groups.sort(key=lambda g: _ORDER.index(g.group) if g.group in _ORDER else 99)
    return chuong3_page, groups
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest experiment/extract/tests/test_sections.py -v`
Expected: PASS (4 passed; SLOW ~90–120s vì mở PDF 103 trang + find_tables — kiên nhẫn). Nếu vắng sample → skipped.

- [ ] **Step 5: Commit**

```bash
git add backend/experiment/extract/sections.py backend/experiment/extract/tests/conftest.py \
        backend/experiment/extract/tests/test_sections.py
git commit -m "feat(experiment): gather Chương III content per main group (Mục 1-4)"
```

---

### Task 3: Markdown render

**Files:**
- Create: `backend/experiment/extract/render.py`
- Test: `backend/experiment/extract/tests/test_render.py`

**Interfaces:**
- Consumes: `Block`, `GroupContent`.
- Produces: `groups_to_markdown(doc:str, chuong3_page:list[int], groups:list[GroupContent]) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/extract/tests/test_render.py
from experiment.extract.schema import Block, GroupContent
from experiment.extract.render import groups_to_markdown


def _grp(**kw):
    base = dict(group="nang_luc", muc="Mục 2. Năng lực", muc_page=[27, 40],
               is_reference=False, ref_target=None, blocks=[])
    base.update(kw)
    return GroupContent(**base)


def test_renders_table_as_markdown():
    g = _grp(blocks=[Block(type="table", page=[28, 28],
                           rows=[["TT", "Mô tả"], ["1", "Lịch sử\nhợp đồng"]])])
    md = groups_to_markdown("E-HSMT", [27, 42], [g])
    assert "| TT | Mô tả |" in md
    assert "| --- | --- |" in md
    assert "Lịch sử hợp đồng" in md  # newline trong ô -> space


def test_renders_reference_note():
    g = _grp(group="ky_thuat", muc="Mục 3. Kỹ thuật",
             is_reference=True, ref_target={"kind": "phan", "number": "4"},
             blocks=[Block(type="text", page=[40, 40], text="Theo Phần 4")])
    md = groups_to_markdown("E-HSMT", [27, 42], [g])
    assert "Tham chiếu" in md and "phan 4" in md.lower()
    assert "Theo Phần 4" in md


def test_renders_text_block():
    g = _grp(group="hop_le", muc="Mục 1. Hợp lệ",
             blocks=[Block(type="text", page=[27, 27], text="E-HSDT hợp lệ khi...")])
    md = groups_to_markdown("E-HSMT", [27, 42], [g])
    assert "E-HSDT hợp lệ khi..." in md
    assert "Mục 1. Hợp lệ" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest experiment/extract/tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'experiment.extract.render'`

- [ ] **Step 3: Create render.py**

```python
# backend/experiment/extract/render.py
"""Render nội dung 4 nhóm ra Markdown cho người đọc/đối chiếu."""
from __future__ import annotations

from .schema import Block, GroupContent


def _cell(s: str | None) -> str:
    return (s or "").replace("\n", " ").replace("|", "\\|").strip()


def _table_md(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    out = []
    header = rows[0] + [""] * (width - len(rows[0]))
    out.append("| " + " | ".join(_cell(c) for c in header) + " |")
    out.append("| " + " | ".join(["---"] * width) + " |")
    for r in rows[1:]:
        r = r + [""] * (width - len(r))
        out.append("| " + " | ".join(_cell(c) for c in r) + " |")
    return "\n".join(out)


def groups_to_markdown(doc: str, chuong3_page: list[int], groups: list[GroupContent]) -> str:
    lines = [f"# Nội dung tiêu chuẩn Chương III — {doc}",
             f"_Chương III: trang {chuong3_page[0]}–{chuong3_page[1]}_", ""]
    for g in groups:
        lines.append(f"## [{g.group}] {g.muc}  (tr {g.muc_page[0]}–{g.muc_page[1]})")
        if g.is_reference and g.ref_target:
            lines.append(f"> ⚠️ Tham chiếu sang **{g.ref_target['kind']} "
                         f"{g.ref_target['number']}** — chưa lần theo ở bước này.")
        lines.append("")
        for b in g.blocks:
            if b.type == "table":
                lines.append(_table_md(b.rows or []))
            else:
                lines.append(b.text or "")
            lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest experiment/extract/tests/test_render.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/experiment/extract/render.py backend/experiment/extract/tests/test_render.py
git commit -m "feat(experiment): render group content to markdown"
```

---

### Task 4: CLI + end-to-end artefacts

**Files:**
- Create: `backend/experiment/extract/cli_extract.py`
- Test: `backend/experiment/extract/tests/test_end_to_end.py`

**Interfaces:**
- Consumes: `build_chuong3_groups`, `groups_to_json`, `groups_to_markdown`.
- Produces: `run(pdf_path:str, out_dir:str) -> dict` (metrics); `main(argv=None)` (argparse `--pdf`, `--out`). Ghi `chuong3_groups.json`, `chuong3_groups.md`, `report.md` vào `out_dir`.

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/extract/tests/test_end_to_end.py
import json

from experiment.extract.cli_extract import run


def test_end_to_end_writes_artefacts(sample_pdf, tmp_path):
    metrics = run(sample_pdf, str(tmp_path))

    data = json.loads((tmp_path / "chuong3_groups.json").read_text(encoding="utf-8"))
    assert (tmp_path / "chuong3_groups.md").exists()
    assert (tmp_path / "report.md").exists()

    assert [g["group"] for g in data["groups"]] == ["hop_le", "nang_luc", "ky_thuat", "tai_chinh"]
    assert metrics["n_groups"] == 4
    assert metrics["nang_luc_has_table"] is True
    assert metrics["ky_thuat_is_reference"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest experiment/extract/tests/test_end_to_end.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'experiment.extract.cli_extract'` (skip nếu vắng sample).

- [ ] **Step 3: Create cli_extract.py**

```python
# backend/experiment/extract/cli_extract.py
"""CLI: HSMT PDF-text -> chuong3_groups.json + .md + report.md (nội dung 4 nhóm Chương III)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .sections import build_chuong3_groups
from .schema import groups_to_json
from .render import groups_to_markdown


def run(pdf_path: str, out_dir: str) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    doc = Path(pdf_path).stem

    chuong3_page, groups = build_chuong3_groups(pdf_path)

    (out / "chuong3_groups.json").write_text(
        groups_to_json(doc, chuong3_page, groups), encoding="utf-8")
    (out / "chuong3_groups.md").write_text(
        groups_to_markdown(doc, chuong3_page, groups), encoding="utf-8")

    by_group = {g.group: g for g in groups}
    metrics = {
        "doc": doc,
        "chuong3_page": chuong3_page,
        "n_groups": len(groups),
        "groups": [g.group for g in groups],
        "nang_luc_has_table": any(
            b.type == "table" for b in by_group.get("nang_luc").blocks
        ) if "nang_luc" in by_group else False,
        "ky_thuat_is_reference": by_group["ky_thuat"].is_reference if "ky_thuat" in by_group else False,
    }

    report = [f"# Báo cáo trích nội dung Chương III — {doc}", "",
              f"- Chương III: trang {chuong3_page[0]}–{chuong3_page[1]}",
              f"- Số nhóm trích được: **{len(groups)}** ({', '.join(metrics['groups'])})", ""]
    for g in groups:
        n_text = sum(1 for b in g.blocks if b.type == "text")
        n_tab = sum(1 for b in g.blocks if b.type == "table")
        ref = f"  ⚠️ tham chiếu {g.ref_target}" if g.is_reference else ""
        report.append(f"- **{g.group}** — {g.muc} (tr {g.muc_page[0]}–{g.muc_page[1]}): "
                      f"{n_text} block text, {n_tab} block bảng{ref}")
    (out / "report.md").write_text("\n".join(report), encoding="utf-8")
    return metrics


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Trích nội dung 4 nhóm tiêu chuẩn Chương III")
    ap.add_argument("--pdf", required=True, help="đường dẫn HSMT PDF-text")
    ap.add_argument("--out", default="experiment/out", help="thư mục artefact")
    args = ap.parse_args(argv)
    metrics = run(args.pdf, args.out)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest experiment/extract/tests/test_end_to_end.py -v`
Expected: PASS (1 passed; hoặc skipped nếu vắng sample). Sau đó chạy CLI thật và soi artefact:

Run: `cd backend && python -m experiment.extract.cli_extract --pdf experiment/samples/E-HSMT.pdf --out experiment/out`
Expected: in JSON metrics (`n_groups=4`, `nang_luc_has_table=true`, `ky_thuat_is_reference=true`); mở `experiment/out/chuong3_groups.md` đọc nội dung 4 nhóm bằng mắt.

- [ ] **Step 5: Commit**

```bash
git add backend/experiment/extract/cli_extract.py backend/experiment/extract/tests/test_end_to_end.py
git commit -m "feat(experiment): CLI + end-to-end extraction of Chương III group content"
```

---

## Acceptance (nghiệm thu bước trích nội dung)

Chạy `cd backend && python -m pytest experiment/extract/tests -v` → tất cả pass (sample tests skip nếu vắng file). Chạy CLI trên `samples/E-HSMT.pdf` và soi `chuong3_groups.md`:

- [ ] Đúng **4 nhóm** theo thứ tự `hop_le, nang_luc, ky_thuat, tai_chinh`, mỗi nhóm gắn đúng Mục + dải trang.
- [ ] **nang_luc** có block `table` giữ nguyên `rows` (header TT/Mô tả/Yêu cầu…, có hàng "1", "2", "3.1"…).
- [ ] **hop_le** có nội dung text điều kiện (p27).
- [ ] **ky_thuat** `is_reference=true`, `ref_target={kind:phan, number:4}`.
- [ ] **tai_chinh** có text phương pháp giá thấp nhất (Bước 1/2/3).
- [ ] Không nhóm nào là Mục 5/6/7.

Đạt hết → chốt bước trích nội dung; sang **bước phân rã tiêu chí** (và lần theo tham chiếu Mục 3 → Phần 4).

## Self-review notes (đã rà)

- **Không LLM**: toàn bộ xác định → verify thật trên máy không có proxy. ✅
- **Giữ rows verbatim**: `_consolidate` đẩy thẳng `TableRegion.rows` vào `Block.rows`, không parse. ✅
- **đ/NFD**: tái dùng `chunking.headings._norm`, không tự viết lại. ✅
- **Mục 5 false-positive** (title chứa "ky thuat"): chặn bằng lọc số Mục ∈ {1,2,3,4} TRƯỚC khi map nhóm. ✅
- **Type consistency**: `build_chuong3_groups -> (list[int], list[GroupContent])`; `groups_to_json/markdown` nhận cùng `(doc, chuong3_page, groups)`; `Block`/`GroupContent` field dùng nhất quán T1↔T2↔T3↔T4. ✅
- **YAGNI**: chưa lần theo tham chiếu (chỉ đánh dấu), chưa phân rã tiêu chí — đúng phạm vi user chốt.
