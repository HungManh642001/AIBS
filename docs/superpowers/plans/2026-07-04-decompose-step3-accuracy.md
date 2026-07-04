# Độ chính xác step-3 decompose: thang leo thang v3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development hoặc superpowers:executing-plans. Steps dùng checkbox (`- [ ]`).

**Goal:** Step-3 (search/resolve) tìm được thông tin CÓ trong corpus mà hiện tại trượt: bỏ cắt cụt bằng chứng, định tuyến need-aware (need "đúng mẫu số N" tra VÀO Biểu mẫu, need giá trị loại Biểu mẫu khỏi lượt tra chung), nạp cả bảng E-BDL làm phụ lục resolve (recall tất định), retry 1 lần có phản hồi khi fail, log lại query/evidence khi `can_review` để đo trên server.

**Architecture:** Chỉ `experiment/` (đo chính xác trước, tích hợp sau). Index mặc định **chỉ loại Chương III (TCĐG), GIỮ Biểu mẫu** (khớp cách server đang chạy) + metadata suy diễn `is_form`/`form_id` lúc build node. Retriever thêm filter `is_form`. Workflow search viết lại thành thang: hits có-chủ-đích (định tuyến theo need) → resolve (kèm phụ lục E-BDL cho need giá trị) → fail thì retry với query mới góc khác, bỏ filter, nới k → fail nữa mới `can_review` + ghi `queries_da_thu`.

**Tech Stack:** Python 3.11, LlamaIndex + Qdrant on-disk, pytest asyncio_mode=auto, ScriptedLlm/scripted retrieve (offline).

## Global Constraints
- **Máy dev KHÔNG có proxy** → mọi test offline (ScriptedLlm + lambda retrieve + DeterministicEmbedding); đo chính xác thật trên server.
- **no-silent-mock:** hết thang vẫn không ra → `can_review`, KHÔNG bịa. LLM lỗi → giữ hành vi hiện tại (log + coi như fail bậc đó).
- **Không phá test cũ:** `test_workflow.py` 8 test hiện có phải xanh nguyên trạng (trừ khi plan nói rõ sửa).
- ScriptedLlm khớp tag ĐẦU TIÊN trong prompt → tag retry phải khác tag lần 1: `[TAG:QUERY2:...]`, `[TAG:RESOLVE2:...]`.
- refs.py đang có dòng `print(...)` debug của user ở module level — XÓA trong Task 2.
- Tiếng Việt comment/nhãn, tiếng Anh code.

---

## Task 1: Index giữ Biểu mẫu + metadata `is_form`/`form_id`

**Files:** Modify `experiment/index/schema.py`; Modify `experiment/index/tests/test_schema.py`.

**Interfaces — Produces:** `is_form_chunk(chunk) -> bool`, `form_id_of(chunk) -> str`; `chunk_to_node` gắn `metadata["is_form"]: bool` (mọi chunk) + `metadata["form_id"]: str` ("" nếu không phải form). `keep_for_index` chỉ loại TCĐG.

- [ ] **Step 1: Sửa test** — trong `test_schema.py` thay test `test_keep_for_index_drops_tcdg_and_bieu_mau` bằng:

```python
def test_keep_for_index_drops_only_tcdg():
    assert not keep_for_index(_c(["PHẦN 4", "Chương III. TIÊU CHUẨN ĐÁNH GIÁ E-HSDT"]))
    # Biểu mẫu GIỮ lại: tiêu chuẩn có thể yêu cầu 'đúng mẫu số N' -> step-3 phải tra được
    assert keep_for_index(_c(["PHẦN 4", "Chương IV. BIỂU MẪU MỜI THẦU VÀ DỰ THẦU"]))
    assert keep_for_index(_c(["PHẦN 4", "Chương II. BẢNG DỮ LIỆU ĐẤU THẦU"]))


def test_chunk_to_node_tags_form_metadata():
    form = _c(["Chương IV. BIỂU MẪU MỜI THẦU VÀ DỰ THẦU"])
    form["text"] = "Mẫu số 01. ĐƠN DỰ THẦU\n..."
    node = chunk_to_node(form)
    assert node.metadata["is_form"] is True and node.metadata["form_id"] == "01"

    normal = _c(["Chương I. CHỈ DẪN NHÀ THẦU"])
    node2 = chunk_to_node(normal)
    assert node2.metadata["is_form"] is False and node2.metadata["form_id"] == ""
```

(Đọc helper `_c` hiện có; nếu không nhận text thì set key sau khi gọi như trên.)

- [ ] **Step 2: Chạy fail** — `pytest experiment/index/tests/test_schema.py -q` → FAIL.
- [ ] **Step 3: Sửa `schema.py`:**

```python
_EXCLUDE_SECTIONS = ("tieu chuan danh gia",)  # CHỈ TCĐG; Biểu mẫu GIỮ (need 'đúng mẫu số N' tra vào)
_FORM_MARK = "bieu mau"
_RE_FORM_ID = re.compile(r"mau\s*(?:so\s*)?(\d+[a-z]?)")  # chạy trên text đã _norm


def is_form_chunk(chunk: dict[str, Any]) -> bool:
    """True nếu chunk thuộc chương Biểu mẫu (mẫu trống cho nhà thầu điền)."""
    return _FORM_MARK in _norm(" ".join(chunk.get("section_path") or []))


def form_id_of(chunk: dict[str, Any]) -> str:
    """Mã mẫu ('01', '04a') từ section_path/đầu text; '' nếu không thấy."""
    hay = _norm(" ".join([*(chunk.get("section_path") or []), (chunk.get("text") or "")[:160]]))
    m = _RE_FORM_ID.search(hay)
    return m.group(1) if m else ""
```
Trong `chunk_to_node`, sau khi dựng `metadata`:
```python
    metadata["is_form"] = is_form_chunk(chunk)
    metadata["form_id"] = form_id_of(chunk) if metadata["is_form"] else ""
```
(`import re` đã cần thêm nếu chưa có.)

- [ ] **Step 4: Chạy pass** — `pytest experiment/index/tests -q` → PASS (cả test_build_e2e vì nó đếm theo `keep_for_index`).
- [ ] **Step 5: Commit** — `fix(index): giữ Biểu mẫu (chỉ loại TCĐG) + metadata is_form/form_id`.

---

## Task 2: `extract_form_refs` + dọn debug print (refs.py)

**Files:** Modify `experiment/decompose/refs.py` (xóa dòng `print(...)` cuối file); Test `experiment/decompose/tests/test_refs.py` (thêm/tạo).

**Interfaces — Produces:** `extract_form_refs(text: str) -> list[str]` — mã mẫu thường hóa (`"01"`, `"04a"`), thứ tự xuất hiện, khử trùng.

- [ ] **Step 1: Test fail**

```python
from experiment.decompose.refs import extract_form_refs


def test_extract_form_refs():
    assert extract_form_refs("Đơn dự thầu phải đúng Mẫu số 01 Chương IV") == ["01"]
    assert extract_form_refs("theo mẫu 04A và Mẫu số 04B") == ["04a", "04b"]
    assert extract_form_refs("Giá trị bảo lãnh theo E-BDL 18.2") == []
    assert extract_form_refs("") == []
```

- [ ] **Step 2:** chạy → FAIL (ImportError).
- [ ] **Step 3: Implement** (kèm XÓA dòng `print(extract_clause_refs(...))` debug):

```python
import unicodedata


def _norm(s: str) -> str:
    s = (s or "").lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


_RE_FORM = re.compile(r"\bmau\s*(?:so\s*)?(\d+[a-z]?)\b")


def extract_form_refs(text: str) -> list[str]:
    """-> mã mẫu ('01','04a') từ 'Mẫu số 01'/'mẫu 04A' — để định tuyến need vào chunk Biểu mẫu."""
    out: list[str] = []
    for m in _RE_FORM.finditer(_norm(text)):
        v = m.group(1)
        if v not in out:
            out.append(v)
    return out
```

- [ ] **Step 4:** chạy → PASS. Kiểm cả `pytest experiment/decompose -q` (không còn print khi import).
- [ ] **Step 5: Commit** — `feat(decompose): extract_form_refs + dọn debug print refs.py`.

---

## Task 3: Retriever filter `is_form`

**Files:** Modify `experiment/decompose/retrieval.py` (`IndexRetriever.__call__`); Test `experiment/decompose/tests/test_retrieval.py` (thêm 1 test theo pattern test hiện có).

**Interfaces — Produces:** `retrieve_fn(query, k, clause_doc=None, is_form=None)` — `is_form=True` chỉ trả chunk Biểu mẫu.

- [ ] **Step 1: Test fail** — theo fixture sẵn có của test_retrieval (đọc file, tái dùng cách dựng index in-memory); nội dung: index 2 node (1 form `is_form=True, form_id="01"`, 1 thường `is_form=False`), gọi `retriever(query, k=5, is_form=True)` → chỉ hit form.
- [ ] **Step 2:** FAIL (TypeError unexpected kwarg).
- [ ] **Step 3: Implement:**

```python
    def __call__(self, query: str, k: int = 5, clause_doc: str | None = None,
                 is_form: bool | None = None) -> list[dict[str, Any]]:
        conds = []
        if clause_doc:
            conds.append(MetadataFilter(key="clause_doc", value=clause_doc, operator=FilterOperator.EQ))
        if is_form is not None:
            conds.append(MetadataFilter(key="is_form", value=is_form, operator=FilterOperator.EQ))
        filters = MetadataFilters(filters=conds) if conds else None
        ...
```

- [ ] **Step 4:** PASS toàn bộ test_retrieval.
- [ ] **Step 5: Commit** — `feat(decompose): IndexRetriever filter is_form`.

---

## Task 4: Prompt retry (QUERY2) + resolve theo attempt (RESOLVE2)

**Files:** Modify `experiment/decompose/prompts.py`.

**Interfaces — Produces:** `retry_query_prompt(crit, need, prev_query) -> str` (tag `[TAG:QUERY2:<nd>]`); `resolve_prompt(crit, need, evidence_text, attempt: int = 1)` — attempt 2 → tag `[TAG:RESOLVE2:<nd>]` (nội dung còn lại giữ nguyên).

- [ ] **Step 1:** Sửa `resolve_prompt` — dòng tag thành:
```python
        f"[TAG:RESOLVE{'' if attempt == 1 else '2'}:{need.get('noi_dung_kiem_tra', '')}]\n"
```
và thêm:
```python
def retry_query_prompt(crit: dict[str, Any], need: dict[str, Any], prev_query: str) -> str:
    """Step search bậc retry — sinh query GÓC KHÁC sau khi lần 1 không ra kết quả."""
    return (
        f"[TAG:QUERY2:{need.get('noi_dung_kiem_tra', '')}]\n"
        f"TIÊU CHÍ: {crit.get('ten')}\n"
        f"YÊU CẦU GỐC (HSMT): {crit.get('yeu_cau_goc', '')}\n"
        f"THÔNG TIN CẦN LÀM RÕ: {need.get('can_lam_ro', '')}\n"
        f"QUERY ĐÃ THỬ (KHÔNG ra kết quả): {prev_query}\n\n"
        "Đặt 1 query KHÁC góc nhìn: từ đồng nghĩa nghiệp vụ khác, hoặc tên NƠI thông tin có thể nằm "
        "(bảng dữ liệu, chỉ dẫn nhà thầu, biểu mẫu, thông báo mời thầu). KHÔNG lặp từ khóa chính cũ.\n"
        + cot_block('{"query":"..."}')
    )
```
- [ ] **Step 2:** Test của Task 5 phủ (prompts thuần build chuỗi); chạy `pytest experiment/decompose -q` xác nhận không vỡ gì.
- [ ] **Step 3: Commit** (gộp vào commit Task 5 nếu muốn, hoặc riêng `feat(decompose): prompt retry QUERY2/RESOLVE2`).

---

## Task 5: Workflow — thang leo thang trong step search

**Files:** Modify `experiment/decompose/workflow.py`; Test thêm vào `experiment/decompose/tests/test_workflow.py`.

**Interfaces:**
- Consumes: Task 2 `extract_form_refs`, Task 3 kwarg `is_form`, Task 4 `retry_query_prompt`/`resolve_prompt(attempt)`.
- Produces: `DecomposeWorkflow(llm_fn, retrieve_fn, timeout, bdl_rows: list[dict] | None = None)`; needs_review entry thêm key `queries_da_thu: {nd: [q1, q2]}` khi có need fail.

**Hành vi mới trong `search` (viết lại vòng `for n in needs`):**
1. Sinh query base (như cũ). `form_refs = extract_form_refs(f"{lam_ro} {n.get('yeu_cau','')}")`.
2. **Need mẫu** (form_refs khác rỗng): `query = base + "mẫu số <id>"*n + "biểu mẫu"`; `hits = _merge_hits(retrieve(query, k=6, is_form=True), retrieve(query, k=3))`; appendix = "" (bảng dữ liệu không liên quan).
3. **Need giá trị**: query như cũ (refs + "bảng dữ liệu E-BDL"); `general = [h for h in retrieve(query, k=6) if not (h.get("metadata") or {}).get("is_form")][:3]`; `hits = _merge_hits(retrieve(query, k=8, clause_doc="bdl"), general)`; appendix = `_bdl_appendix()`.
4. `_try_resolve(crit, n, hits, appendix, attempt=1)` — resolve chạy cả khi hits rỗng miễn có appendix (giá trị có thể nằm trong bảng); thành công → điền `thong_tin_bo_sung`/`nguon`, xong need.
5. Fail → **retry**: `retry_query_prompt` (fallback `f"{lam_ro} {ten}"` nếu LLM lỗi) → `hits2 = retrieve(query2 + refs, k=10)` (KHÔNG filter — phủ cả Biểu mẫu/E-CDNT/TBMT) → `_try_resolve(..., attempt=2)`.
6. Fail nữa → `n["_queries_da_thu"] = [query, query2]`; đoạn no-fab cuối: pop key này vào `chi_tiet[nd]`, needs_review entry thêm `"queries_da_thu": chi_tiet` + `log.warning` kèm đầu evidence.

**Code chèn (constants + helpers ở class/module):**
```python
_EVIDENCE_CAP = 9000   # ký tự bằng chứng hits (NGUYÊN VĂN chunk, không cắt 300)
_BDL_CAP = 15000       # trần phụ lục bảng E-BDL
```
```python
    def _bdl_appendix(self) -> str:
        """Toàn bộ dòng E-BDL (nếu được cấp) — recall tất định cho giá trị data-sheet."""
        if not self._bdl_rows:
            return ""
        return "\n".join(r.get("text", "") for r in self._bdl_rows)[:_BDL_CAP]

    @staticmethod
    def _evidence(hits: list[dict]) -> str:
        out, used = [], 0
        for h in hits or []:
            t = h.get("text", "")
            take = t[: _EVIDENCE_CAP - used]
            out.append(take)
            used += len(take)
            if used >= _EVIDENCE_CAP:
                break
        return "\n".join(out)

    async def _try_resolve(self, crit: dict, n: dict, hits: list[dict], appendix: str,
                           attempt: int) -> bool:
        """Resolve 1 lượt; True nếu điền được thong_tin_bo_sung (no-fab: can_review -> False)."""
        if not hits and not appendix:
            return False
        body = self._evidence(hits)
        if appendix:
            body = f"{body}\n\n[PHỤ LỤC — BẢNG DỮ LIỆU (E-BDL) ĐẦY ĐỦ]\n{appendix}"
        rout = await self._llm(SYS_RESOLVE, resolve_prompt(crit, n, body, attempt=attempt),
                               validate=validate_resolved_value, max_tokens=_STRUCT_MAX_TOKENS)
        if rout.status == "ok" and not rout.data.get("can_review") \
                and (rout.data.get("thong_tin_bo_sung") or "").strip():
            n["thong_tin_bo_sung"] = rout.data["thong_tin_bo_sung"]
            n["nguon"] = rout.data.get("nguon", "") or self._hit_source(hits)
            return True
        if rout.status == "error":
            log.warning("    [search] %s/%s -> lỗi resolve(%d): %s",
                        crit.get("ten", ""), n.get("noi_dung_kiem_tra", ""), attempt, rout.error)
        return False
```

**Tests mới (3):**
```python
async def test_search_form_need_routes_into_bieu_mau():
    """Need 'đúng mẫu số 01' -> retrieve VÀO Biểu mẫu (is_form=True) + neo mã mẫu."""
    captured: list[dict] = []

    def retrieve_fn(q, k=5, clause_doc=None, is_form=None):
        captured.append({"q": q, "is_form": is_form, "clause_doc": clause_doc})
        if is_form:
            return [{"text": "Mẫu số 01. ĐƠN DỰ THẦU: gồm tên nhà thầu, giá dự thầu, hiệu lực...",
                     "metadata": {"chunk_id": "f1", "is_form": True, "form_id": "01"}, "score": 1.0}]
        return []

    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Đơn dự thầu"}]},
        "[TAG:STRUCT:Đơn dự thầu]": _crit(
            "Đơn dự thầu", [_nd("Đúng mẫu quy định", can_lam_ro="Mẫu số 01 Chương IV")]),
        "[TAG:QUERY:Đúng mẫu quy định]": {"query": "mẫu đơn dự thầu"},
        "[TAG:RESOLVE:Đúng mẫu quy định]":
            {"thong_tin_bo_sung": "Theo Mẫu số 01: tên nhà thầu, giá dự thầu, hiệu lực",
             "nguon": "Mẫu số 01 Chương IV", "can_review": False},
    })
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=retrieve_fn, timeout=30)
    gd = await wf.run(group=_GROUP)

    form_calls = [c for c in captured if c["is_form"]]
    assert form_calls and "mẫu số 01" in form_calls[0]["q"].lower()
    assert not any(c["clause_doc"] == "bdl" for c in captured)  # need mẫu KHÔNG đi đường bdl
    nd = _nd_by(_by_name(gd.criteria, "Đơn dự thầu"), "Đúng mẫu quy định")
    assert nd["thong_tin_bo_sung"].startswith("Theo Mẫu số 01") and nd["can_review"] is False


async def test_search_bdl_appendix_resolves_without_hits():
    """Retrieve trượt hoàn toàn nhưng giá trị nằm trong bảng E-BDL nạp kèm -> vẫn resolve được."""
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Bảo đảm dự thầu"}]},
        "[TAG:STRUCT:Bảo đảm dự thầu]": _crit(
            "Bảo đảm dự thầu", [_nd("Giá trị bảo lãnh", can_lam_ro="Giá trị bảo lãnh")]),
        "[TAG:QUERY:Giá trị bảo lãnh]": {"query": "giá trị bảo đảm"},
        "[TAG:RESOLVE:Giá trị bảo lãnh]":
            {"thong_tin_bo_sung": "Giá trị: 6.100.000 VNĐ", "nguon": "E-BDL 18.2", "can_review": False},
    })
    bdl = [{"text": "E-CDNT 18.2 | Giá trị bảo đảm 6.100.000 VNĐ", "clause_doc": "bdl"}]
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5, clause_doc=None, is_form=None: [],
                           timeout=30, bdl_rows=bdl)
    gd = await wf.run(group=_GROUP)

    nd = _nd_by(_by_name(gd.criteria, "Bảo đảm dự thầu"), "Giá trị bảo lãnh")
    assert nd["thong_tin_bo_sung"] == "Giá trị: 6.100.000 VNĐ" and nd["can_review"] is False
    resolves = [c for c in llm.calls if "[TAG:RESOLVE:" in c]
    assert resolves and "PHỤ LỤC — BẢNG DỮ LIỆU" in resolves[0] and "6.100.000" in resolves[0]


async def test_search_retry_second_query_succeeds_and_logs():
    """Bậc retry: lần 1 không ra -> QUERY2 góc khác, retrieve KHÔNG filter -> RESOLVE2 đậu."""
    calls: list[dict] = []

    def retrieve_fn(q, k=5, clause_doc=None, is_form=None):
        calls.append({"q": q, "k": k, "clause_doc": clause_doc, "is_form": is_form})
        if "chủ đầu tư" in q:   # chỉ query góc mới mới ra
            return [{"text": "Tên Chủ đầu tư: Vietsovpetro",
                     "metadata": {"chunk_id": "x", "source_doc": "hsmt"}, "score": 1.0}]
        return []

    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Bảo đảm dự thầu"}]},
        "[TAG:STRUCT:Bảo đảm dự thầu]": _crit(
            "Bảo đảm dự thầu", [_nd("Đơn vị thụ hưởng", can_lam_ro="Đơn vị thụ hưởng bảo lãnh")]),
        "[TAG:QUERY:Đơn vị thụ hưởng]": {"query": "đơn vị thụ hưởng bảo lãnh"},
        "[TAG:QUERY2:Đơn vị thụ hưởng]": {"query": "tên chủ đầu tư bên mời thầu"},
        "[TAG:RESOLVE2:Đơn vị thụ hưởng]":
            {"thong_tin_bo_sung": "Đơn vị thụ hưởng = Chủ đầu tư: Vietsovpetro",
             "nguon": "E-BDL 1.1", "can_review": False},
    })
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=retrieve_fn, timeout=30)
    gd = await wf.run(group=_GROUP)

    nd = _nd_by(_by_name(gd.criteria, "Bảo đảm dự thầu"), "Đơn vị thụ hưởng")
    assert nd["can_review"] is False and "Vietsovpetro" in nd["thong_tin_bo_sung"]
    retry = [c for c in calls if c["clause_doc"] is None and c["is_form"] is None and c["k"] == 10]
    assert retry and "chủ đầu tư" in retry[0]["q"]        # retry: bỏ filter + nới k
    assert any("[TAG:QUERY2:" in c for c in llm.calls)     # đã hỏi query góc mới
    assert gd.needs_review == []
```
Và cập nhật test cũ `test_critique_adds_missing_and_no_fabrication`: sau needs_review thêm assert `"queries_da_thu" in gd.needs_review[0]` (need fail cả 2 bậc → có log query).

- [ ] **Step 1:** Thêm 3 test + assert mới → chạy `pytest experiment/decompose/tests/test_workflow.py -q` → FAIL.
- [ ] **Step 2:** Implement (constructor nhận `bdl_rows`, viết lại vòng needs theo hành vi 1-6, helpers trên, cập nhật đoạn no-fab gom `queries_da_thu`).
- [ ] **Step 3:** `pytest experiment/decompose -q` → PASS (test cũ + mới).
- [ ] **Step 4: Commit** — `feat(decompose): thang leo thang step-3 (need-aware + phụ lục E-BDL + retry)`.

---

## Task 6: Nối `bdl_rows` từ chunks + multisource

**Files:** Modify `experiment/decompose/run_decompose.py`; Modify `experiment/multisource/run_rubric.py`; Tests: `experiment/decompose/tests/test_run_chunks.py` (mới), sửa `experiment/multisource/tests/test_run_rubric.py`.

**Interfaces — Produces:** `run_decompose.run(..., chunks_path: str | None = None)`; helper `_load_bdl_rows(chunks_path) -> list[dict]` (lọc `clause_doc=="bdl"`); CLI `--chunks` default `out/chunks.jsonl`; `run_multi` truyền `chunks_path=<chunks_merged.jsonl>`.

- [ ] **Step 1: Test fail**

```python
# experiment/decompose/tests/test_run_chunks.py
import json

from experiment.decompose.run_decompose import _load_bdl_rows


def test_load_bdl_rows_filters_clause_doc(tmp_path):
    p = tmp_path / "chunks.jsonl"
    rows = [
        {"chunk_id": "a", "text": "E-CDNT 18.2 | 6.100.000", "clause_doc": "bdl"},
        {"chunk_id": "b", "text": "quy tắc", "clause_doc": "cdnt"},
        {"chunk_id": "c", "text": "text thường"},
    ]
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    got = _load_bdl_rows(str(p))
    assert [r["chunk_id"] for r in got] == ["a"]
    assert _load_bdl_rows(str(tmp_path / "missing.jsonl")) == []
    assert _load_bdl_rows(None) == []
```
Và trong `test_run_rubric.py` sửa `fake_decompose` + assert:
```python
    async def fake_decompose(groups_path, db_path, out_dir, **kw):
        calls.append("decompose")
        assert str(kw.get("chunks_path", "")).endswith("chunks_merged.jsonl")
        return {"n_criteria": 0}
```

- [ ] **Step 2:** FAIL (ImportError `_load_bdl_rows`; multisource assert fail).
- [ ] **Step 3: Implement** — `run_decompose.py`:

```python
def _load_bdl_rows(chunks_path: str | None) -> list[dict[str, Any]]:
    """Đọc chunks.jsonl -> các dòng Bảng dữ liệu (clause_doc='bdl') cho phụ lục resolve."""
    if not chunks_path:
        return []
    p = Path(chunks_path)
    if not p.exists():
        return []
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [c for c in rows if c.get("clause_doc") == "bdl"]
```
`run(...)` thêm param `chunks_path: str | None = None`; trước vòng groups: `bdl_rows = _load_bdl_rows(chunks_path)`; khởi tạo `DecomposeWorkflow(..., bdl_rows=bdl_rows or None)`; log số dòng. CLI: `ap.add_argument("--chunks", default="out/chunks.jsonl")` → `run(..., chunks_path=args.chunks)`.
`run_rubric.py`: `decompose_run(..., chunks_path=merged)`.

- [ ] **Step 4:** `pytest experiment/decompose experiment/multisource -q` → PASS.
- [ ] **Step 5: Commit** — `feat(decompose): nạp bdl_rows từ chunks vào workflow (+multisource)`.

---

## Verification
1. **Offline:** `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/index experiment/decompose experiment/multisource -q` → xanh toàn bộ.
2. **Server (đo chính xác):** chạy lại pipeline trên HSMT thật (`run_rubric` hoặc `run_decompose --chunks out/chunks.jsonl`), so `decomposition.md` trước/sau:
   - Các need từng `⚠️cần soi` dù giá trị CÓ trong HSMT → giờ resolve được (đếm `n_needs_review` giảm).
   - Need "đúng mẫu số N" → `thong_tin_bo_sung` chứa nội dung mẫu + `nguon` = "Mẫu số N...".
   - Need còn fail → `needs_review[].queries_da_thu` cho biết đã thử gì → phân biệt retrieval trượt vs resolve từ chối (soi log `[search]`).
3. Không đụng backend/frontend (`services/rubric_pipeline` gọi `decompose_run` không truyền `chunks_path` → bdl_rows rỗng, hành vi cũ — tích hợp sau khi đo đạt).

## Ghi chú
- Giữ Biểu mẫu làm corpus to hơn (~+80%) → bù nhiễu bằng: need giá trị loại `is_form` ở lượt tra chung + bdl-first như cũ; retry mới mở toàn corpus.
- `_queries_da_thu` là key tạm trong dict need, PHẢI pop trước khi item vào kết quả (schema sạch).
- Index cũ trên server (thiếu `is_form`) cần **re-index** sau bản này (mỗi run vốn build lại → tự có).
