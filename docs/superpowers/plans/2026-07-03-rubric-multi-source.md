# Rubric đa nguồn (Sub-project A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) hoặc superpowers:executing-plans để thực thi từng task. Steps dùng checkbox (`- [ ]`).

**Goal:** Bước decompose resolve được các giá trị/mốc thời gian công bố ở "Thông báo mời thầu" (TBMT — pdf scan riêng) bằng cách OCR scan → index chung với HSMT, gắn nguồn (provenance), thay vì bỏ sót → `can_review`.

**Architecture:** Chỉ làm trong `experiment/` (chưa đụng backend/frontend) để **đo độ chính xác luồng trước**. Thêm **cầu nối OCR** (vision đọc scan → chunk dict tương thích `chunks.jsonl`), **gộp nguồn** (gắn `source_doc`), và **quy nguồn** (`_hit_source` ghi "Thông báo mời thầu tr N"). Trích tiêu chí (Chương III) vẫn CHỈ từ HSMT; TBMT chỉ góp vào index tra-giá-trị (step-3 search). Không sửa chunker HSMT (gắn `source_doc` ở ranh giới gộp — metadata tự chảy qua `chunk_to_node`).

**Tech Stack:** Python 3.11, PyMuPDF (fitz), LlamaIndex + Qdrant on-disk (hybrid BM25+dense), LiteLLM proxy → Qwen3.6 27B (vision OCR + LLM + embeddings), pytest (asyncio_mode=auto).

## Global Constraints
- **Máy dev KHÔNG có proxy** (vision/LLM/embeddings đều Qwen3.6 27B qua `localhost:4000`). Test offline: `ScriptedVision` (OCR), `ScriptedLlm`/scripted retrieve (decompose), `DeterministicEmbedding`+BM25 (index). **Không chạy end-to-end thật ở dev** — đo chính xác thật trên server.
- **no-silent-mock:** OCR/tra cứu không ra → để trống + `can_review`/`cần soi`, KHÔNG bịa. Vision lỗi → bỏ qua trang đó (text="") + log.
- **Ảnh gửi vision là base64 inline** (tái dùng `experiment/evaluate/vision.default_vision_fn`, không internet).
- **Không sửa chunker HSMT** (`experiment/chunking/*`) — gắn `source_doc` ở bước gộp.
- Tiếng Việt trong comment/nhãn, tiếng Anh trong code.
- Chunk dict tương thích: `experiment/index/schema.chunk_to_node` chỉ cần `chunk_id`+`text`, phần còn lại → metadata; `keep_for_index` đọc `section_path` (không được chứa "tieu chuan danh gia"/"bieu mau").

---

## File Structure
- Create `experiment/multisource/__init__.py` — package rỗng.
- Create `experiment/multisource/ocr_chunks.py` — OCR scan → list chunk dict (source_doc). **Task 1**.
- Create `experiment/multisource/merge.py` — gộp chunks HSMT + OCR, gắn `source_doc="hsmt"` mặc định. **Task 2**.
- Modify `experiment/decompose/workflow.py` (`_hit_source`) — quy nguồn theo `source_doc` khi không có mã điều khoản. **Task 3**.
- Create `experiment/multisource/run_rubric.py` — orchestrator đa nguồn (chunk HSMT + OCR TBMT + merge + index + decompose) + hướng dẫn đo chính xác. **Task 4**.
- Tests: `experiment/multisource/tests/test_ocr_chunks.py`, `test_merge.py`, `test_run_rubric.py`; sửa `experiment/decompose/tests/test_workflow.py`.

---

## Task 1: Cầu nối OCR scan → chunk dict

**Files:**
- Create: `experiment/multisource/__init__.py` (rỗng), `experiment/multisource/ocr_chunks.py`
- Test: `experiment/multisource/tests/test_ocr_chunks.py` (+ `experiment/multisource/tests/__init__.py` rỗng)

**Interfaces — Produces:**
- `async ocr_scan_to_chunks(pdf_path: str, source_doc: str, vision_fn=None, dpi: int = 200, max_chars: int = 600) -> list[dict]` — mỗi phần text (≤max_chars) 1 chunk dict: `{chunk_id, text, section_path, page_start, page_end, node_type, group_hint, source_doc, clause_id, clause_doc, doc}`.
- `SYS_OCR: str`, `ocr_prompt() -> str`, `validate_ocr(d) -> dict` (schema `{text}`).
- `_split_text(text: str, max_chars: int) -> list[str]`.

- [ ] **Step 1: Write the failing test**

```python
# experiment/multisource/tests/test_ocr_chunks.py
import fitz

from experiment.evaluate.vision import ScriptedVision
from experiment.multisource.ocr_chunks import SYS_OCR, ocr_scan_to_chunks, _split_text


def _pdf(text: str) -> bytes:
    d = fitz.open()
    d.new_page().insert_htmlbox(fitz.Rect(72, 72, 500, 300), f"<p>{text}</p>")
    return d.tobytes()


def test_split_text_windows():
    parts = _split_text("a" * 700 + "\n" + "b" * 100, max_chars=600)
    assert len(parts) >= 2 and all(len(p) <= 600 for p in parts)


async def test_ocr_scan_to_chunks(tmp_path):
    pdf = tmp_path / "tbmt.pdf"
    pdf.write_bytes(_pdf("Thông báo mời thầu"))
    vision = ScriptedVision({SYS_OCR: {"text": "Thời điểm đóng thầu 09h00 ngày 20/05/2026"}})

    chunks = await ocr_scan_to_chunks(str(pdf), source_doc="tbmt", vision_fn=vision)

    assert chunks and all(c["source_doc"] == "tbmt" for c in chunks)
    c = chunks[0]
    assert "đóng thầu" in c["text"] and c["page_start"] == 1
    assert c["section_path"] == ["Thông báo mời thầu"] and c["node_type"] == "text"
    assert c["chunk_id"].startswith("tbmt-")
    # tương thích index: chỉ cần chunk_id + text; source_doc/page vào metadata
    from experiment.index.schema import chunk_to_node, keep_for_index
    assert keep_for_index(c) is True
    node = chunk_to_node(c)
    assert node.metadata["source_doc"] == "tbmt" and node.text == c["text"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/multisource/tests/test_ocr_chunks.py -q`
Expected: FAIL (ModuleNotFoundError `experiment.multisource.ocr_chunks`).

- [ ] **Step 3: Write the implementation**

```python
# experiment/multisource/ocr_chunks.py
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
    "Bạn đọc ẢNH một trang tài liệu mời thầu (scan, tiếng Việt). BÓC TOÀN BỘ chữ thành text, "
    "giữ chính xác số/ngày/giờ/đơn vị, KHÔNG bịa, KHÔNG tóm tắt. Chỉ trả JSON {\"text\": \"...\"}."
)

# nhãn người đọc cho section_path theo source_doc
_SECTION = {"tbmt": "Thông báo mời thầu"}


def ocr_prompt() -> str:
    return "[OCR] Trả JSON: {\"text\":\"<toàn bộ chữ trong ảnh>\"}"


def validate_ocr(d: dict[str, Any]) -> dict[str, Any]:
    return {"text": str(d.get("text", "") or "")}


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
        for i, part in enumerate(_split_text(out.data.get("text", ""), max_chars)):
            chunks.append({
                "chunk_id": f"{source_doc}-p{page}-{i}", "text": part,
                "section_path": [section], "page_start": page, "page_end": page,
                "node_type": "text", "group_hint": "unknown",
                "source_doc": source_doc, "clause_id": "", "clause_doc": "",
                "doc": source_doc,
            })
    return chunks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/multisource/tests/test_ocr_chunks.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/experiment/multisource/__init__.py backend/experiment/multisource/ocr_chunks.py backend/experiment/multisource/tests/
git commit -m "feat(multisource): cầu nối OCR scan -> chunk dict (source_doc)"
```

---

## Task 2: Gộp nguồn — chunks HSMT + OCR, gắn source_doc

**Files:**
- Create: `experiment/multisource/merge.py`
- Test: `experiment/multisource/tests/test_merge.py`

**Interfaces:**
- Consumes: chunk dict từ Task 1; `chunks.jsonl` do `experiment/chunking/cli_chunk` sinh (dict/line).
- Produces: `merge_chunk_files(hsmt_jsonl: str, extra_chunks: list[dict], out_jsonl: str, hsmt_source: str = "hsmt") -> int` — ghi file gộp, gắn `source_doc=hsmt_source` cho chunk HSMT nếu thiếu; trả tổng số chunk.

- [ ] **Step 1: Write the failing test**

```python
# experiment/multisource/tests/test_merge.py
import json

from experiment.multisource.merge import merge_chunk_files


def test_merge_tags_source_and_appends(tmp_path):
    hsmt = tmp_path / "chunks.jsonl"
    hsmt.write_text(
        json.dumps({"chunk_id": "hsmt-1", "text": "E-CDNT ...", "section_path": ["Chỉ dẫn"]}) + "\n",
        encoding="utf-8")
    extra = [{"chunk_id": "tbmt-p1-0", "text": "đóng thầu 09h00", "section_path": ["Thông báo mời thầu"],
              "source_doc": "tbmt"}]
    out = tmp_path / "merged.jsonl"

    n = merge_chunk_files(str(hsmt), extra, str(out))

    lines = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert n == 2 and len(lines) == 2
    by_id = {c["chunk_id"]: c for c in lines}
    assert by_id["hsmt-1"]["source_doc"] == "hsmt"      # gắn mặc định
    assert by_id["tbmt-p1-0"]["source_doc"] == "tbmt"   # giữ nguyên
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/multisource/tests/test_merge.py -q`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Write the implementation**

```python
# experiment/multisource/merge.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/multisource/tests/test_merge.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/experiment/multisource/merge.py backend/experiment/multisource/tests/test_merge.py
git commit -m "feat(multisource): gộp chunks HSMT + OCR, gắn source_doc"
```

---

## Task 3: Quy nguồn `_hit_source` theo source_doc (TBMT)

**Files:**
- Modify: `experiment/decompose/workflow.py` (`_hit_source` staticmethod, ~dòng 144-153)
- Test: `experiment/decompose/tests/test_workflow.py` (thêm 1 test)

**Interfaces:**
- Consumes: hit dict `{text, metadata, score}` (metadata gồm `clause_id/clause_doc/source_doc/page_start`).
- Produces (đổi hành vi `_hit_source`): ưu tiên mã điều khoản (E-BDL/E-CDNT); nếu không có → nếu hit thuộc `source_doc != "hsmt"` trả `"<nhãn> tr <page>"` (vd `"Thông báo mời thầu tr 1"`).

- [ ] **Step 1: Write the failing test**

```python
# thêm vào experiment/decompose/tests/test_workflow.py
from experiment.decompose.workflow import DecomposeWorkflow


def test_hit_source_attributes_tbmt_when_no_clause():
    # có mã điều khoản -> ưu tiên mã (giữ hành vi cũ)
    clause = [{"metadata": {"clause_id": "18.2", "clause_doc": "bdl"}}]
    assert DecomposeWorkflow._hit_source(clause) == "E-BDL 18.2"
    # không có mã, thuộc TBMT -> quy về tài liệu + trang
    tbmt = [{"metadata": {"source_doc": "tbmt", "page_start": 1}}]
    assert DecomposeWorkflow._hit_source(tbmt) == "Thông báo mời thầu tr 1"
    # HSMT không mã điều khoản -> "" (không quy nguồn theo tài liệu)
    assert DecomposeWorkflow._hit_source([{"metadata": {"source_doc": "hsmt"}}]) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/decompose/tests/test_workflow.py::test_hit_source_attributes_tbmt_when_no_clause -q`
Expected: FAIL (`AssertionError`: trả "" cho TBMT).

- [ ] **Step 3: Sửa `_hit_source`** (thay nguyên staticmethod hiện tại)

```python
    _SOURCE_LABELS = {"tbmt": "Thông báo mời thầu"}  # source_doc -> nhãn người đọc

    @staticmethod
    def _hit_source(hits: list[dict]) -> str:
        """nguon: ưu tiên mã điều khoản (E-BDL/E-CDNT); không có -> quy theo tài liệu nguồn (TBMT...)."""
        for h in hits or []:
            m = h.get("metadata") or {}
            cid = m.get("clause_id")
            if cid:
                prefix = "E-BDL" if m.get("clause_doc") == "bdl" else "E-CDNT"
                return f"{prefix} {cid}"
        for h in hits or []:  # không có mã điều khoản -> nguồn theo tài liệu (không phải HSMT)
            m = h.get("metadata") or {}
            src = m.get("source_doc")
            if src and src != "hsmt":
                label = DecomposeWorkflow._SOURCE_LABELS.get(src, src)
                page = m.get("page_start")
                return f"{label} tr {page}" if page else label
        return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/decompose/tests/test_workflow.py -q`
Expected: PASS (mọi test workflow cũ + test mới).

- [ ] **Step 5: Commit**

```bash
git add backend/experiment/decompose/workflow.py backend/experiment/decompose/tests/test_workflow.py
git commit -m "feat(decompose): _hit_source quy nguồn theo source_doc (TBMT tr N)"
```

---

## Task 4: Orchestrator đa nguồn + quy trình đo chính xác

**Files:**
- Create: `experiment/multisource/run_rubric.py`
- Test: `experiment/multisource/tests/test_run_rubric.py`

**Interfaces:**
- Consumes: `experiment.chunking.cli_chunk.run` (HSMT→chunks.jsonl), `experiment.extract.cli_extract.run` (HSMT→chuong3_groups.json), `experiment.index.build_index.run`, `experiment.decompose.run_decompose.run`, `ocr_scan_to_chunks` (Task 1), `merge_chunk_files` (Task 2).
- Produces: `async run_multi(hsmt_pdf: str, scan_sources: list[tuple[str, str]], out_dir: str, vision_fn=None, embed=None, llm_fn=None, retrieve_fn=None) -> dict` — `scan_sources` = `[(source_doc, pdf_path)]`. Chuỗi: chunk HSMT → OCR mỗi scan → merge → index → decompose; trả metrics decompose.

- [ ] **Step 1: Write the failing test** (test wiring bằng monkeypatch, không cần proxy/PDF thật)

```python
# experiment/multisource/tests/test_run_rubric.py
import json

import experiment.multisource.run_rubric as rr


async def test_run_multi_orchestration(tmp_path, monkeypatch):
    calls = []

    def fake_chunk(pdf, out):  # tạo chunks.jsonl HSMT giả
        p = f"{out}/chunks.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps({"chunk_id": "hsmt-1", "text": "E-CDNT", "section_path": ["Chỉ dẫn"]}) + "\n")
        calls.append("chunk"); return {"n_chunks": 1}

    def fake_extract(pdf, out):
        with open(f"{out}/chuong3_groups.json", "w", encoding="utf-8") as f:
            json.dump({"doc": "HSMT", "groups": []}, f)
        calls.append("extract"); return {}

    async def fake_ocr(pdf_path, source_doc, vision_fn=None, **kw):
        calls.append(f"ocr:{source_doc}")
        return [{"chunk_id": "tbmt-p1-0", "text": "đóng thầu 09h00", "section_path": ["Thông báo mời thầu"],
                 "source_doc": "tbmt"}]

    def fake_index(chunks_path, db_path, out_dir, **kw):
        n = sum(1 for _ in open(chunks_path, encoding="utf-8"))
        calls.append(f"index:{n}"); return {"n_points": n}

    async def fake_decompose(groups_path, db_path, out_dir, **kw):
        calls.append("decompose"); return {"n_criteria": 0}

    monkeypatch.setattr(rr, "chunk_run", fake_chunk)
    monkeypatch.setattr(rr, "extract_run", fake_extract)
    monkeypatch.setattr(rr, "ocr_scan_to_chunks", fake_ocr)
    monkeypatch.setattr(rr, "index_run", fake_index)
    monkeypatch.setattr(rr, "decompose_run", fake_decompose)

    hsmt = tmp_path / "hsmt.pdf"; hsmt.write_bytes(b"%PDF-1.4")
    tbmt = tmp_path / "tbmt.pdf"; tbmt.write_bytes(b"%PDF-1.4")

    metrics = await rr.run_multi(str(hsmt), [("tbmt", str(tbmt))], str(tmp_path / "out"))

    assert calls == ["chunk", "extract", "ocr:tbmt", "index:2", "decompose"]  # thứ tự + merge (2 chunk)
    assert metrics["n_criteria"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/multisource/tests/test_run_rubric.py -q`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Write the implementation**

```python
# experiment/multisource/run_rubric.py
"""Orchestrator RUBRIC ĐA NGUỒN (experiment) — đo chính xác trước khi tích hợp backend.

Chuỗi: chunk HSMT (pdf-text) -> OCR mỗi tài liệu scan (TBMT...) -> gộp chunks (source_doc) ->
build index (mọi nguồn) -> decompose. Trích tiêu chí (Chương III) CHỈ từ HSMT; scan chỉ góp giá trị.

Đo chính xác (server có proxy): chạy có TBMT vs không TBMT, so trong decomposition.md các nội dung
về thời gian (đóng thầu/hiệu lực): PASS nếu thong_tin_bo_sung được điền + nguon="Thông báo mời thầu tr N";
FAIL nếu còn '⚠️cần soi' (can_review). no-silent-mock: bước nào lỗi (proxy tắt) -> raise, không bịa.
"""
from __future__ import annotations

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from experiment.chunking.cli_chunk import run as chunk_run
from experiment.extract.cli_extract import run as extract_run
from experiment.index.build_index import run as index_run
from experiment.decompose.run_decompose import run as decompose_run
from experiment.multisource.merge import merge_chunk_files
from experiment.multisource.ocr_chunks import ocr_scan_to_chunks

log = logging.getLogger("experiment.multisource")


async def run_multi(hsmt_pdf: str, scan_sources: list[tuple[str, str]], out_dir: str,
                    vision_fn: Any | None = None, embed: Any | None = None,
                    llm_fn: Any | None = None, retrieve_fn: Any | None = None) -> dict[str, Any]:
    """HSMT + danh sách (source_doc, scan_pdf) -> decomposition.json (đa nguồn). Trả metrics decompose."""
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)

    log.info("[multi] (1/5) chunk HSMT")
    chunk_run(hsmt_pdf, str(out))                       # -> out/chunks.jsonl
    log.info("[multi] (2/5) extract Chương III (HSMT)")
    extract_run(hsmt_pdf, str(out))                     # -> out/chuong3_groups.json

    extra: list[dict] = []
    for source_doc, pdf in scan_sources:
        log.info("[multi] (3/5) OCR %s", source_doc)
        extra.extend(await ocr_scan_to_chunks(pdf, source_doc=source_doc, vision_fn=vision_fn))

    merged = str(out / "chunks_merged.jsonl")
    n = merge_chunk_files(str(out / "chunks.jsonl"), extra, merged)
    log.info("[multi] (4/5) build index: %d chunk (%d nguồn scan)", n, len(scan_sources))
    index_run(chunks_path=merged, db_path=str(out / "qdrant"), out_dir=str(out), embed=embed)

    log.info("[multi] (5/5) decompose")
    return await decompose_run(groups_path=str(out / "chuong3_groups.json"),
                               db_path=str(out / "qdrant"), out_dir=str(out),
                               llm_fn=llm_fn, retrieve_fn=retrieve_fn)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rubric đa nguồn (HSMT + scan mời thầu)")
    ap.add_argument("--hsmt", required=True, help="HSMT pdf-text")
    ap.add_argument("--scan", nargs="*", default=[], help="các nguồn scan <source_doc>=<đường_dẫn.pdf>")
    ap.add_argument("--out", default="experiment/out_multi")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(message)s", stream=sys.stderr)
    sources: list[tuple[str, str]] = []
    for spec in args.scan:
        if "=" not in spec:
            print(f"[run_rubric] --scan cần <source_doc>=<đường_dẫn>: {spec}", file=sys.stderr)
            return 2
        sd, path = spec.split("=", 1)
        sources.append((sd.strip(), path))
    try:
        metrics = asyncio.run(run_multi(args.hsmt, sources, args.out))
    except Exception as exc:  # no-silent-mock
        print(f"[run_rubric] LỖI: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("  Chế độ thật cần LiteLLM proxy (vision OCR + LLM + embeddings).", file=sys.stderr)
        return 2
    import json
    print(json.dumps(metrics, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/multisource/tests/test_run_rubric.py -q`
Expected: PASS.

- [ ] **Step 5: Run cả suite multisource + decompose (không regress)**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/multisource experiment/decompose -q`
Expected: tất cả PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/experiment/multisource/run_rubric.py backend/experiment/multisource/tests/test_run_rubric.py
git commit -m "feat(multisource): orchestrator rubric đa nguồn + đo chính xác"
```

---

## Verification (đo chính xác — mục tiêu chính)
1. **Offline (dev, không proxy):** `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/multisource experiment/decompose -q` → xanh. Chứng minh cơ chế OCR-bridge + merge + attribution + orchestration đúng.
2. **Server (có proxy) — đo chính xác thật:**
   - Chuẩn bị `E-HSMT.pdf` (pdf-text) + `TBMT.pdf` (scan) có mốc thời gian (đóng thầu/phát hành).
   - **Baseline (không TBMT):** `python3 -m experiment.multisource.run_rubric --hsmt E-HSMT.pdf --out out_base` → mở `out_base/decomposition.md`, ghi lại các nội dung về thời gian: kỳ vọng **⚠️cần soi** (can_review, vì HSMT không có).
   - **Đa nguồn:** `python3 -m experiment.multisource.run_rubric --hsmt E-HSMT.pdf --scan tbmt=TBMT.pdf --out out_multi` → mở `out_multi/decomposition.md`.
   - **Tiêu chí PASS:** các nội dung thời gian giờ có `thông tin bổ sung` = giá trị thật + `[nguồn: Thông báo mời thầu tr N]`, KHÔNG còn ⚠️cần soi. So số `n_needs_review` giảm so với baseline.
   - Ghi kết quả (accuracy) để quyết định có tích hợp backend (đổi `services/rubric_pipeline.build_decomposition` sang đa nguồn) hay chỉnh thêm.

## Ghi chú
- Chỉ đụng `experiment/`; backend/frontend giữ nguyên (tích hợp là bước sau, sau khi đo chính xác đạt).
- OCR chunk cắt ≤600 ký tự để `resolve` (đọc `hit["text"][:300]`) không mất giá trị.
- TBMT thuộc corpus "mời thầu" (HSMT-side) → giá trị của nó là chuẩn để HSDT phải thỏa (đúng luồng `can_tra_cuu` HSMT-side sẵn có; không cần đổi step analyze).
- Sub-project B (registry luật liên-tài-liệu) là plan riêng, làm sau khi A đo chính xác đạt.
