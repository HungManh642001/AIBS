# AI Accuracy Remediation (P0+P1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the AI pipeline from fabricating verdicts on failure (surface errors), locate TCĐG/BDS by section-range, extract the rubric in two map-reduce steps, and prompt with Chain-of-Thought — without breaking the mock demo path.

**Architecture:** A new `ai_call` returns a typed `AiOutcome{status,data,model,error}` instead of silently returning mock on any exception. JSON is extracted from CoT responses by a dedicated `extract_json`, validated by Pydantic models, and failures (`status="error"`) flow to a new `ket_qua="ERROR"` verdict that the UI surfaces and that blocks report export. The locator returns explicit page ranges with `located` flags (no wrong-content fallback). Rubric extraction becomes a coordinator that lists criteria first, then details each one, with structure-aware chunking.

**Tech Stack:** Python 3 + FastAPI + SQLAlchemy 2.x + SQLite; pydantic v2 / pydantic-settings; LiteLLM Proxy → Qwen3-27B (mock fallback only when `ABES_AI_MOCK=1`); React + Vite + AntD v5 + Tailwind (frontend verified statically — node is unavailable in this WSL env).

## Global Constraints

- Response/return convention for FastAPI endpoints: `{"success": bool, "data": ..., "error": ...}` via `responses.ok`/`responses.fail`.
- Vietnamese in UI/comments, English in code identifiers.
- `async/await` for all I/O; type hints mandatory; PEP 8 / snake_case.
- No DB migration tool — adding the string value `"ERROR"` to `ket_qua` requires **no** schema change.
- **Mock is intentional only** (`settings.ai_mock` / `ABES_AI_MOCK=1`). Real mode must NEVER return mock data on failure — it returns `status="error"`.
- Drop `response_format={"type":"json_object"}` (it blocks Chain-of-Thought).
- Run backend tests with: `cd backend && pytest`.
- Out of scope (do NOT implement): P2 deterministic-number fixes in `checks.py`, P3 grounding/anti-injection, manual page-range picker UI, Alembic.

---

### Task 1: Config settings for AI tuning

**Files:**
- Modify: `backend/config.py:9-17`
- Test: `backend/tests/test_config_ai.py` (create)

**Interfaces:**
- Produces: `settings.ai_temperature: float`, `settings.ai_max_tokens: int`, `settings.ai_max_tokens_extract: int`, `settings.ai_chunk_chars: int`, `settings.ai_chunk_overlap: int`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_config_ai.py`:

```python
from config import Settings


def test_ai_tuning_defaults():
    s = Settings()
    assert s.ai_temperature == 0.0
    assert s.ai_max_tokens == 4096
    assert s.ai_max_tokens_extract == 8192
    assert s.ai_chunk_chars == 12000
    assert s.ai_chunk_overlap == 800
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_config_ai.py -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'ai_temperature'`

- [ ] **Step 3: Add the settings**

In `backend/config.py`, after the `ai_mock` line (line 17), add inside the `Settings` class:

```python
    ai_temperature: float = 0.0                    # 0 -> tái lập kết quả
    ai_max_tokens: int = 4096                       # giới hạn token sinh (đánh giá/sub-check)
    ai_max_tokens_extract: int = 8192              # token cho bước liệt kê tiêu chí (output dài)
    ai_chunk_chars: int = 12000                     # ngân sách ký tự mỗi chunk
    ai_chunk_overlap: int = 800                     # overlap giữa các chunk
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_config_ai.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/config.py backend/tests/test_config_ai.py
git commit -m "feat: add AI tuning settings (temperature, max_tokens, chunking)"
```

---

### Task 2: JSON extraction + page_ref utilities

**Files:**
- Create: `backend/services/json_utils.py`
- Test: `backend/tests/test_json_utils.py` (create)

**Interfaces:**
- Produces: `extract_json(raw: str) -> dict` (raises `ValueError` if no JSON object can be recovered); `clamp_page_refs(refs, max_page: int = 0) -> list[int]`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_json_utils.py`:

```python
import pytest
from services.json_utils import extract_json, clamp_page_refs


def test_extract_plain_object():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_from_fence():
    raw = "Suy luận: ok\n```json\n{\"result\": \"PASS\"}\n```"
    assert extract_json(raw) == {"result": "PASS"}


def test_extract_ignores_prose_around_object():
    raw = 'Tôi kết luận như sau: {"x": [1, 2]} . Hết.'
    assert extract_json(raw) == {"x": [1, 2]}


def test_extract_strips_trailing_comma():
    assert extract_json('{"a": 1, "b": [2, 3,],}') == {"a": 1, "b": [2, 3]}


def test_extract_nested_braces():
    assert extract_json('{"a": {"b": 1}}') == {"a": {"b": 1}}


def test_extract_empty_raises():
    with pytest.raises(ValueError):
        extract_json("")


def test_extract_no_object_raises():
    with pytest.raises(ValueError):
        extract_json("không có json ở đây")


def test_clamp_filters_and_bounds():
    assert clamp_page_refs([1, 2, "x", 0, -3, True], max_page=3) == [1, 2]
    assert clamp_page_refs([1, 9], max_page=3) == [1]
    assert clamp_page_refs([1, 9], max_page=0) == [1, 9]   # 0 = không biết số trang -> chỉ lọc >=1
    assert clamp_page_refs(None, max_page=3) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_json_utils.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.json_utils'`

- [ ] **Step 3: Implement the module**

Create `backend/services/json_utils.py`:

```python
"""Bóc JSON từ phản hồi LLM (có Chain-of-Thought) và chuẩn hoá page_ref."""
from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _strip_trailing_commas(s: str) -> str:
    return _TRAILING_COMMA.sub(r"\1", s)


def extract_json(raw: str) -> dict[str, Any]:
    """Bóc object JSON ngoài cùng. Ưu tiên khối ```json fence; ném ValueError nếu thất bại."""
    if not raw or not raw.strip():
        raise ValueError("Phản hồi AI rỗng")
    text = raw.strip()
    m = _FENCE.search(text)
    if m:
        text = m.group(1).strip()

    start = text.find("{")
    if start == -1:
        raise ValueError("Không tìm thấy JSON object trong phản hồi")

    depth = 0
    in_str = False
    esc = False
    end = -1
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        raise ValueError("JSON object không cân bằng ngoặc")

    candidate = _strip_trailing_commas(text[start:end])
    return json.loads(candidate)


def clamp_page_refs(refs: Any, max_page: int = 0) -> list[int]:
    """Giữ lại các số trang hợp lệ (int >= 1, <= max_page nếu max_page > 0). Bỏ bool/non-int."""
    out: list[int] = []
    for r in refs or []:
        if isinstance(r, bool) or not isinstance(r, int):
            continue
        if r < 1:
            continue
        if max_page and r > max_page:
            continue
        out.append(r)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_json_utils.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/services/json_utils.py backend/tests/test_json_utils.py
git commit -m "feat: add JSON extraction + page_ref clamp utilities"
```

---

### Task 3: Pydantic validation schemas

**Files:**
- Create: `backend/services/ai_schemas.py`
- Test: `backend/tests/test_ai_schemas.py` (create)

**Interfaces:**
- Produces validator callables `dict -> dict` (raise on structural failure):
  `validate_eval_verdict`, `validate_sub_verdict`, `validate_validate_artifact`, `validate_criteria_list`, `validate_criterion_detail`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_ai_schemas.py`:

```python
import pytest
from services import ai_schemas


def test_eval_verdict_ok():
    out = ai_schemas.validate_eval_verdict(
        {"evidence": "có chữ ký", "result": "PASS", "score": 90, "page_ref": [1]})
    assert out["result"] == "PASS" and out["score"] == 90


def test_eval_verdict_missing_required_raises():
    with pytest.raises(Exception):
        ai_schemas.validate_eval_verdict({"score": 90})  # thiếu evidence + result


def test_sub_verdict_ok():
    out = ai_schemas.validate_sub_verdict({"evidence": "x", "result": "FAIL"})
    assert out["result"] == "FAIL" and out["page_ref"] == []


def test_criteria_list_ok():
    out = ai_schemas.validate_criteria_list(
        {"criteria": [{"nhom": "hop_le", "ten": "Đơn dự thầu", "required_artifacts": ["don_du_thau"]}]})
    assert out["criteria"][0]["ten"] == "Đơn dự thầu"


def test_criteria_list_item_without_ten_raises():
    with pytest.raises(Exception):
        ai_schemas.validate_criteria_list({"criteria": [{"nhom": "hop_le"}]})


def test_criterion_detail_ok():
    out = ai_schemas.validate_criterion_detail({
        "ten": "Bảo đảm dự thầu",
        "sub_checks": [{"ten": "Có bảo đảm", "check_type": "presence",
                        "required_artifact": "bao_dam_du_thau", "blocking": True}]})
    assert out["sub_checks"][0]["blocking"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_ai_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.ai_schemas'`

- [ ] **Step 3: Implement the schemas**

Create `backend/services/ai_schemas.py`:

```python
"""Pydantic schema validate output AI. Sai cấu trúc -> ném lỗi -> ai_call coi là error."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


class EvalVerdictModel(_Base):
    evidence: str
    result: str
    score: float = 0.0
    page_ref: list[Any] = []
    note: str = ""


class SubVerdictModel(_Base):
    evidence: str
    result: str
    page_ref: list[Any] = []


class ValidateArtifactModel(_Base):
    match: bool
    suggested_type: str = ""
    confidence: float = 0.0
    note: str = ""


class CriterionListItem(_Base):
    nhom: str = "hop_le"
    ten: str
    required_artifacts: list[Any] = []


class CriteriaListModel(_Base):
    criteria: list[CriterionListItem]


class SubCheckModel(_Base):
    ten: str
    check_type: str = ""
    thong_so: dict[str, Any] = {}
    required_artifact: str = ""
    blocking: bool = True


class CriterionDetailModel(_Base):
    nhom: str = "hop_le"
    ten: str
    yeu_cau: str = ""
    required_artifacts: list[Any] = []
    kieu: str = "pass_fail"
    trong_so: float = 0.0
    sub_checks: list[SubCheckModel] = []
    proposed_artifacts: list[Any] = []


def validate_eval_verdict(d: dict[str, Any]) -> dict[str, Any]:
    return EvalVerdictModel(**d).model_dump()


def validate_sub_verdict(d: dict[str, Any]) -> dict[str, Any]:
    return SubVerdictModel(**d).model_dump()


def validate_validate_artifact(d: dict[str, Any]) -> dict[str, Any]:
    return ValidateArtifactModel(**d).model_dump()


def validate_criteria_list(d: dict[str, Any]) -> dict[str, Any]:
    return CriteriaListModel(**d).model_dump()


def validate_criterion_detail(d: dict[str, Any]) -> dict[str, Any]:
    return CriterionDetailModel(**d).model_dump()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_ai_schemas.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/services/ai_schemas.py backend/tests/test_ai_schemas.py
git commit -m "feat: add Pydantic validation schemas for AI output"
```

---

### Task 4: `ai_call` with typed outcome (no silent mock)

**Files:**
- Modify: `backend/services/ai_client.py:69-115`
- Test: `backend/tests/test_ai_call.py` (create)

**Interfaces:**
- Consumes: `extract_json` (Task 2).
- Produces:
  - `AiOutcome` dataclass: `status: str` ("ok"|"error"), `data: dict | None`, `model: str`, `error: str | None`.
  - `async ai_call(system: str, prompt: str, *, mock_key: str, validate=None, max_tokens: int | None = None) -> AiOutcome`.
  - `_litellm_completion(system, prompt, max_tokens=None)` now sends `temperature`/`max_tokens`, no `response_format`.
- Note: `ai_json` is KEPT in this task (callers migrate in Tasks 7,9,12; removed in Task 13).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_ai_call.py`:

```python
import pytest
from services import ai_client


@pytest.mark.asyncio
async def test_mock_returns_ok_outcome(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)
    out = await ai_client.ai_call("sys", "p", mock_key="eval_subcheck")
    assert out.status == "ok"
    assert out.model == "mock"
    assert out.data["result"] in {"PASS", "FAIL", "PARTIAL"}


@pytest.mark.asyncio
async def test_real_parse_failure_retries_then_errors(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)
    calls = {"n": 0}

    def garbage(*a, **k):
        calls["n"] += 1
        return "đây không phải JSON"

    monkeypatch.setattr(ai_client, "_litellm_completion", garbage)
    out = await ai_client.ai_call("sys", "p", mock_key="eval_subcheck")
    assert out.status == "error"
    assert out.data is None
    assert calls["n"] == 2   # initial + 1 retry
    assert out.model != "mock"


@pytest.mark.asyncio
async def test_real_success_parses_fenced_json(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)
    monkeypatch.setattr(ai_client, "_litellm_completion",
                        lambda *a, **k: 'Suy luận...\n```json\n{"result":"PASS","evidence":"ok","page_ref":[1]}\n```')
    out = await ai_client.ai_call("sys", "p", mock_key="eval_subcheck")
    assert out.status == "ok"
    assert out.data["result"] == "PASS"


@pytest.mark.asyncio
async def test_validate_failure_becomes_error(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)
    monkeypatch.setattr(ai_client, "_litellm_completion",
                        lambda *a, **k: '{"result":"PASS"}')   # thiếu evidence

    def validate(d):
        if "evidence" not in d:
            raise ValueError("thiếu evidence")
        return d

    out = await ai_client.ai_call("sys", "p", mock_key="eval_subcheck", validate=validate)
    assert out.status == "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_ai_call.py -v`
Expected: FAIL with `AttributeError: module 'services.ai_client' has no attribute 'ai_call'`

- [ ] **Step 3: Implement `AiOutcome` + `ai_call`, update `_litellm_completion`**

In `backend/services/ai_client.py`, update the imports block at the top (after `from typing import Any`) to add:

```python
from dataclasses import dataclass
from typing import Any, Callable

from services.json_utils import extract_json
```

Replace the body of `_litellm_completion` (lines 69-90) so the `litellm.completion(...)` call drops `response_format` and adds tuning. The new function:

```python
def _litellm_completion(system: str, prompt: str, max_tokens: int | None = None) -> str:
    """Gọi LiteLLM Proxy (OpenAI-compatible /v1). Tách riêng để test dễ monkeypatch."""
    import litellm

    model = settings.ai_model
    if "/" not in model:
        model = f"openai/{model}"

    resp = litellm.completion(
        model=model,
        api_base=settings.ai_base_url,
        api_key=settings.ai_api_key or "sk-no-key",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=settings.ai_temperature,
        max_tokens=max_tokens or settings.ai_max_tokens,
        timeout=300,
    )
    return resp["choices"][0]["message"]["content"]
```

Then, immediately after `_litellm_completion` and BEFORE `async def ai_json`, insert:

```python
@dataclass
class AiOutcome:
    """Kết quả 1 lượt gọi AI. status='error' nghĩa là KHÔNG có dữ liệu thật (không bịa mock)."""
    status: str            # "ok" | "error"
    data: dict[str, Any] | None
    model: str             # tên model thật | "mock"
    error: str | None = None


async def ai_call(
    system: str,
    prompt: str,
    *,
    mock_key: str,
    validate: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    max_tokens: int | None = None,
) -> AiOutcome:
    """Gọi AI và trả AiOutcome. Mock CHỈ khi ai_mock=1; chế độ thật lỗi -> status='error'."""
    if settings.ai_mock:
        data = copy.deepcopy(MOCK_RESPONSES[mock_key])
        if validate is not None:
            data = validate(data)
        return AiOutcome(status="ok", data=data, model="mock")

    last_err = ""
    for attempt in range(2):  # lần đầu + 1 retry
        try:
            raw = _litellm_completion(system, prompt, max_tokens=max_tokens)
            data = extract_json(raw)
            if validate is not None:
                data = validate(data)
            logger.info("AI[%s]: TRẢ KẾT QUẢ THẬT (model=%s).", mock_key, settings.ai_model)
            return AiOutcome(status="ok", data=data, model=settings.ai_model)
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            logger.warning("AI[%s]: lượt %d THẤT BẠI: %s", mock_key, attempt + 1, last_err)

    return AiOutcome(status="error", data=None, model=settings.ai_model, error=last_err)
```

(Leave `ai_json` and `_mock` unchanged for now.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_ai_call.py tests/test_ai_client.py -v`
Expected: PASS (new file 4 passed; existing `test_ai_client.py` still passes — `ai_json` untouched)

- [ ] **Step 5: Commit**

```bash
git add backend/services/ai_client.py backend/tests/test_ai_call.py
git commit -m "feat: ai_call with typed AiOutcome, no silent mock fallback"
```

---

### Task 5: Chain-of-Thought prompt helpers

**Files:**
- Create: `backend/services/prompts.py`
- Test: `backend/tests/test_prompts.py` (create)

**Interfaces:**
- Produces: `cot_block(schema_hint: str, scale: str = "") -> str` — instruction telling the model to reason first, then emit one fenced JSON object; `SCALE_DEF` constant with PASS/FAIL/PARTIAL definitions.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_prompts.py`:

```python
from services.prompts import cot_block, SCALE_DEF


def test_cot_block_demands_reasoning_then_json():
    b = cot_block('{"result":"..."}')
    assert "suy luận" in b.lower()
    assert "```json" in b
    assert '{"result":"..."}' in b


def test_cot_block_includes_scale_when_given():
    b = cot_block('{"x":1}', scale=SCALE_DEF)
    assert "PASS" in b and "FAIL" in b and "PARTIAL" in b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_prompts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.prompts'`

- [ ] **Step 3: Implement the helpers**

Create `backend/services/prompts.py`:

```python
"""Mẫu prompt Chain-of-Thought dùng chung cho trích xuất & đánh giá."""
from __future__ import annotations

SCALE_DEF = (
    "Thang kết quả: "
    "PASS = đáp ứng đầy đủ yêu cầu; "
    "FAIL = vi phạm điều kiện tiên quyết hoặc thiếu yêu cầu bắt buộc; "
    "PARTIAL = đáp ứng một phần. "
    "Trích đúng nguyên văn câu/điều khoản làm dẫn chứng (evidence). "
)


def cot_block(schema_hint: str, scale: str = "") -> str:
    """Trả khối hướng dẫn: suy luận trước, rồi xuất DUY NHẤT một khối JSON trong fence."""
    parts = [
        "Hãy suy luận ngắn gọn theo các bước: "
        "(1) đọc yêu cầu, (2) đối chiếu nội dung hồ sơ, (3) kết luận.",
    ]
    if scale:
        parts.append(scale)
    parts.append(
        "Sau phần suy luận, xuất DUY NHẤT một khối JSON đặt trong ```json ... ```. "
        "Trong JSON, ghi evidence/lý do TRƯỚC result. "
        f"Cấu trúc JSON: {schema_hint}"
    )
    return "\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_prompts.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/services/prompts.py backend/tests/test_prompts.py
git commit -m "feat: add Chain-of-Thought prompt helpers"
```

---

### Task 6: Locate TCĐG/BDS by section range

**Files:**
- Modify: `backend/services/hsmt_locator.py` (full rewrite)
- Test: `backend/tests/test_hsmt_locator.py` (rewrite)

**Interfaces:**
- Produces: `locate_hsmt_sections(hsmt_pages: list[dict]) -> dict` returning
  `{"tcdg": {"located": bool, "pages": list[dict]}, "bds": {"located": bool, "pages": list[dict]}}`.
  No fallback to whole document; `located=false` ⇒ `pages=[]`.

- [ ] **Step 1: Rewrite the failing test**

Replace the entire contents of `backend/tests/test_hsmt_locator.py`:

```python
from services.hsmt_locator import locate_hsmt_sections

PAGES = [
    {"page": 1, "text": "Chương I. Bảng dữ liệu đấu thầu. Giá trị bảo đảm dự thầu: 150 triệu"},
    {"page": 2, "text": "Tiếp tục bảng dữ liệu, các mục BDS chi tiết"},
    {"page": 3, "text": "Chương III. Tiêu chuẩn đánh giá về tính hợp lệ"},
    {"page": 4, "text": "Bảng tiêu chí năng lực tiếp theo (vẫn thuộc tiêu chuẩn đánh giá)"},
]


def test_tcdg_is_a_range_to_end():
    out = locate_hsmt_sections(PAGES)
    assert out["tcdg"]["located"] is True
    assert [p["page"] for p in out["tcdg"]["pages"]] == [3, 4]


def test_bds_range_stops_before_next_heading():
    out = locate_hsmt_sections(PAGES)
    assert out["bds"]["located"] is True
    assert [p["page"] for p in out["bds"]["pages"]] == [1, 2]


def test_matches_despite_missing_diacritics():
    pages = [{"page": 1, "text": "CHUONG III. TIEU CHUAN DANH GIA ho so du thau"}]
    out = locate_hsmt_sections(pages)
    assert out["tcdg"]["located"] is True
    assert [p["page"] for p in out["tcdg"]["pages"]] == [1]


def test_not_located_returns_empty_no_fallback():
    pages = [{"page": 1, "text": "không có heading chuẩn nào cả"}]
    out = locate_hsmt_sections(pages)
    assert out["tcdg"]["located"] is False and out["tcdg"]["pages"] == []
    assert out["bds"]["located"] is False and out["bds"]["pages"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_hsmt_locator.py -v`
Expected: FAIL (old return shape: `out["tcdg"]` is a list, has no `["located"]`)

- [ ] **Step 3: Rewrite the locator**

Replace the entire contents of `backend/services/hsmt_locator.py`:

```python
"""Định vị mục Tiêu chuẩn đánh giá (TCĐG) + Bảng dữ liệu đấu thầu (BDS) trong HSMT lớn.

Trả dải trang (từ heading bắt đầu đến heading mục lớn kế tiếp), không lấy lẻ trang,
và KHÔNG fallback nạp toàn bộ tài liệu khi không định vị được.
"""
from __future__ import annotations

import unicodedata

# Heading nhận diện (đã bỏ dấu, lowercase) — so khớp trên text đã chuẩn hoá.
_TCDG_KW = ["tieu chuan danh gia"]
_BDS_KW = ["bang du lieu dau thau", "bang du lieu", "bds"]
# Heading "mục lớn" để biết một dải kết thúc ở đâu.
_SECTION_KW = _TCDG_KW + _BDS_KW + ["chuong ", "phan ", "muc "]


def _norm(text: str) -> str:
    """Lowercase + bỏ dấu tiếng Việt để chống lỗi OCR/biến thể."""
    nfkd = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def _starts(norm_text: str, keywords: list[str]) -> bool:
    return any(k in norm_text for k in keywords)


def _range_from(pages: list[dict], norms: list[str], start_kw: list[str]) -> dict:
    """Tìm trang bắt đầu (chứa heading start_kw); lấy đến trước heading mục lớn kế tiếp."""
    start = next((i for i, n in enumerate(norms) if _starts(n, start_kw)), None)
    if start is None:
        return {"located": False, "pages": []}
    end = len(pages)
    for j in range(start + 1, len(pages)):
        # Kết thúc khi gặp heading mục lớn KHÁC (không thuộc cùng nhóm start_kw).
        if _starts(norms[j], _SECTION_KW) and not _starts(norms[j], start_kw):
            end = j
            break
    return {"located": True, "pages": pages[start:end]}


def locate_hsmt_sections(hsmt_pages: list[dict]) -> dict:
    """Định vị TCĐG và BDS thành dải trang.

    Returns:
        {"tcdg": {"located": bool, "pages": [...]},
         "bds":  {"located": bool, "pages": [...]}}
    """
    norms = [_norm(p.get("text", "")) for p in hsmt_pages]
    return {
        "tcdg": _range_from(hsmt_pages, norms, _TCDG_KW),
        "bds": _range_from(hsmt_pages, norms, _BDS_KW),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_hsmt_locator.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/services/hsmt_locator.py backend/tests/test_hsmt_locator.py
git commit -m "feat: locate TCĐG/BDS by section range, no whole-doc fallback"
```

---

### Task 7: Two-step rubric extraction with chunking

**Files:**
- Modify: `backend/services/extraction.py` (rewrite `extract_rubric`, add `chunk_pages`, `_list_criteria`, `_detail_criterion`, `_merge_criteria`; keep `extract_criteria`/`map_hsdt` for now)
- Test: `backend/tests/test_extract_rubric.py` (rewrite), `backend/tests/test_chunking.py` (create)

**Interfaces:**
- Consumes: `ai_call`/`AiOutcome` (Task 4), `cot_block`/`SCALE_DEF` (Task 5), `validate_criteria_list`/`validate_criterion_detail` (Task 3), `clamp_page_refs` (Task 2), new locator shape (Task 6).
- Produces:
  - `async extract_rubric(sections: dict) -> AiOutcome` — `sections` is the new locator output (`{"tcdg":{"located","pages"},"bds":{...}}`). `data={"criteria":[...]}` on ok.
  - `chunk_pages(pages: list[dict], max_chars: int, overlap: int) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_chunking.py`:

```python
from services.extraction import chunk_pages, _merge_criteria


def test_chunk_pages_splits_on_budget():
    pages = [{"page": i, "text": "x" * 5000} for i in range(1, 5)]
    chunks = chunk_pages(pages, max_chars=12000, overlap=0)
    assert len(chunks) >= 2
    assert all(len(c) <= 12000 + 200 for c in chunks)  # cộng nhãn [Trang N]


def test_chunk_pages_single_when_small():
    pages = [{"page": 1, "text": "ngắn"}]
    assert len(chunk_pages(pages, max_chars=12000, overlap=0)) == 1


def test_merge_criteria_dedupes_by_normalized_ten():
    a = [{"ten": "Đơn dự thầu"}, {"ten": "Bảo đảm dự thầu"}]
    b = [{"ten": "DON DU THAU"}, {"ten": "Hợp đồng tương tự"}]
    merged = _merge_criteria([a, b])
    tens = [c["ten"] for c in merged]
    assert tens == ["Đơn dự thầu", "Bảo đảm dự thầu", "Hợp đồng tương tự"]
```

Replace the entire contents of `backend/tests/test_extract_rubric.py`:

```python
import pytest
from services import extraction, ai_client


@pytest.fixture(autouse=True)
def force_mock(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", True)


@pytest.mark.asyncio
async def test_extract_rubric_mock_shortcircuits():
    sections = {"tcdg": {"located": True, "pages": [{"page": 3, "text": "Tiêu chuẩn đánh giá"}]},
                "bds": {"located": True, "pages": [{"page": 1, "text": "Giá trị bảo đảm: 150 triệu"}]}}
    out = await extraction.extract_rubric(sections)
    assert out.status == "ok"
    crit = out.data["criteria"]
    bdt = next(c for c in crit if c["ten"] == "Bảo đảm dự thầu")
    assert bdt["required_artifacts"] == ["bao_dam_du_thau"]


@pytest.mark.asyncio
async def test_two_step_runs_in_real_mode(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)

    async def fake_list(tcdg_pages):
        return ai_client.AiOutcome("ok", {"criteria": [
            {"nhom": "hop_le", "ten": "Đơn dự thầu", "required_artifacts": ["don_du_thau"]}]}, "qwen3-27b")

    async def fake_detail(crit, tcdg_chunk, bds_pages):
        return ai_client.AiOutcome("ok", {
            "nhom": "hop_le", "ten": crit["ten"], "required_artifacts": crit["required_artifacts"],
            "sub_checks": [{"ten": "Có đơn", "check_type": "presence",
                            "required_artifact": "don_du_thau", "blocking": True}]}, "qwen3-27b")

    monkeypatch.setattr(extraction, "_list_criteria", fake_list)
    monkeypatch.setattr(extraction, "_detail_criterion", fake_detail)
    sections = {"tcdg": {"located": True, "pages": [{"page": 3, "text": "TCĐG"}]},
                "bds": {"located": True, "pages": []}}
    out = await extraction.extract_rubric(sections)
    assert out.status == "ok"
    assert out.data["criteria"][0]["sub_checks"][0]["check_type"] == "presence"


@pytest.mark.asyncio
async def test_list_step_error_propagates(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)

    async def fake_list(tcdg_pages):
        return ai_client.AiOutcome("error", None, "qwen3-27b", "boom")

    monkeypatch.setattr(extraction, "_list_criteria", fake_list)
    sections = {"tcdg": {"located": True, "pages": [{"page": 3, "text": "TCĐG"}]},
                "bds": {"located": True, "pages": []}}
    out = await extraction.extract_rubric(sections)
    assert out.status == "error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_chunking.py tests/test_extract_rubric.py -v`
Expected: FAIL (`chunk_pages`/`_merge_criteria` not defined; `extract_rubric` returns list not `AiOutcome`)

- [ ] **Step 3: Rewrite `extract_rubric` and add helpers**

In `backend/services/extraction.py`, update the import block at the top (replace `from services.ai_client import ai_json`):

```python
from services.ai_client import ai_json, ai_call, AiOutcome
from services import artifact_catalog
from services.json_utils import clamp_page_refs
from services.prompts import cot_block, SCALE_DEF
from services.ai_schemas import validate_criteria_list, validate_criterion_detail
from config import get_settings

_settings = get_settings()
```

Replace the `_SYS_RUBRIC` constant and the `extract_rubric` function (lines 45-69) with:

```python
_SYS_RUBRIC_LIST = (
    "Bạn là chuyên gia đấu thầu theo Luật Đấu thầu Việt Nam. Đọc Tiêu chuẩn đánh giá (TCĐG) "
    "và LIỆT KÊ các tiêu chí đánh giá. Mỗi tiêu chí gồm: nhom (hop_le/nang_luc/ky_thuat/tai_chinh), "
    "ten, và required_artifacts (mã loại hồ sơ theo danh mục cho sẵn)."
)
_SYS_RUBRIC_DETAIL = (
    "Bạn là chuyên gia đấu thầu theo Luật Đấu thầu Việt Nam. Với MỘT tiêu chí đánh giá, bóc tách "
    "thành các điểm kiểm con (sub_checks) kèm check_type và ngưỡng (thong_so). Khi tiêu chí tham chiếu "
    "'theo yêu cầu HSMT', tra số cụ thể trong BẢNG DỮ LIỆU ĐẤU THẦU (BDS) và ghi nguồn (thong_so.nguon); "
    "nếu không tìm được, đặt thong_so.can_review=true."
)


def chunk_pages(pages: list[dict[str, Any]], max_chars: int, overlap: int) -> list[str]:
    """Cắt danh sách trang thành các chunk theo ranh giới TRANG (không cắt giữa trang), có overlap."""
    blocks = [f"[Trang {p['page']}]\n{p.get('text', '')}" for p in pages]
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for b in blocks:
        if cur and cur_len + len(b) > max_chars:
            chunks.append("\n".join(cur))
            # overlap: giữ lại phần đuôi của chunk trước
            tail = "\n".join(cur)[-overlap:] if overlap else ""
            cur = [tail] if tail else []
            cur_len = len(tail)
        cur.append(b)
        cur_len += len(b)
    if cur:
        chunks.append("\n".join(cur))
    return chunks or [""]


def _norm_ten(ten: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFD", (ten or "").lower().strip())
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def _merge_criteria(lists: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Gộp danh sách tiêu chí từ nhiều chunk, khử trùng theo ten (chuẩn hoá bỏ dấu)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for lst in lists:
        for c in lst:
            key = _norm_ten(c.get("ten", ""))
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(c)
    return out


def _catalog_codes() -> str:
    return ", ".join(
        f"{c}={artifact_catalog.get_artifact(c)['label']}" for c in artifact_catalog.all_codes()
    )


async def _list_criteria(tcdg_pages: list[dict[str, Any]]) -> AiOutcome:
    """Bước 1: liệt kê tiêu chí từ dải TCĐG; chunk + merge nếu quá ngân sách."""
    chunks = chunk_pages(tcdg_pages, _settings.ai_chunk_chars, _settings.ai_chunk_overlap)
    lists: list[list[dict[str, Any]]] = []
    for ch in chunks:
        prompt = (
            f"Danh mục loại hồ sơ (code=label): {_catalog_codes()}\n\n"
            f"TIÊU CHUẨN ĐÁNH GIÁ:\n{ch}\n\n"
            + cot_block('{"criteria":[{"nhom","ten","required_artifacts":[...]}]}')
        )
        out = await ai_call(_SYS_RUBRIC_LIST, prompt, mock_key="extract_rubric",
                            validate=validate_criteria_list,
                            max_tokens=_settings.ai_max_tokens_extract)
        if out.status == "error":
            return out
        lists.append(out.data.get("criteria", []))
    return AiOutcome("ok", {"criteria": _merge_criteria(lists)}, chunks and "qwen3-27b" or "qwen3-27b")


async def _detail_criterion(
    crit: dict[str, Any], tcdg_text: str, bds_text: str, max_page: int
) -> AiOutcome:
    """Bước 2: chi tiết sub_checks + ngưỡng cho MỘT tiêu chí."""
    prompt = (
        f"Danh mục loại hồ sơ (code=label): {_catalog_codes()}\n\n"
        f"TIÊU CHÍ: {crit.get('ten')} (nhóm {crit.get('nhom', 'hop_le')})\n\n"
        f"TIÊU CHUẨN ĐÁNH GIÁ:\n{tcdg_text}\n\n"
        f"BẢNG DỮ LIỆU ĐẤU THẦU:\n{bds_text}\n\n"
        + cot_block(
            '{"nhom","ten","yeu_cau","required_artifacts":[...],"kieu","trong_so",'
            '"sub_checks":[{"ten","check_type","thong_so","required_artifact","blocking"}],'
            '"proposed_artifacts":[]}',
            scale=SCALE_DEF,
        )
    )
    out = await ai_call(_SYS_RUBRIC_DETAIL, prompt, mock_key="extract_rubric",
                        validate=validate_criterion_detail,
                        max_tokens=_settings.ai_max_tokens_extract)
    return out


async def extract_rubric(sections: dict[str, Any]) -> AiOutcome:
    """Điều phối trích xuất 2 bước. sections = output locator mới.

    Mock chủ ý: trả thẳng mock 'extract_rubric'. Chế độ thật: liệt kê -> chi tiết từng tiêu chí.
    """
    if _settings.ai_mock:
        return await ai_call("", "", mock_key="extract_rubric")

    tcdg = sections.get("tcdg", {})
    bds = sections.get("bds", {})
    tcdg_pages = tcdg.get("pages", [])
    bds_pages = bds.get("pages", [])
    max_page = max((int(p.get("page", 0)) for p in tcdg_pages + bds_pages), default=0)

    listed = await _list_criteria(tcdg_pages)
    if listed.status == "error":
        return listed

    tcdg_text = "\n".join(f"[Trang {p['page']}]\n{p.get('text', '')}" for p in tcdg_pages)
    bds_text = "\n".join(f"[Trang {p['page']}]\n{p.get('text', '')}" for p in bds_pages)

    detailed: list[dict[str, Any]] = []
    for crit in listed.data.get("criteria", []):
        d = await _detail_criterion(crit, tcdg_text, bds_text, max_page)
        if d.status == "error":
            # Lỗi 1 tiêu chí: đánh dấu can_review, vẫn giữ tiêu chí để chuyên gia xử lý.
            detailed.append({**crit, "sub_checks": [], "proposed_artifacts": [],
                             "can_review": True, "loi_ai": d.error})
            continue
        item = d.data
        if not bds.get("located", False):
            for sc in item.get("sub_checks", []):
                sc.setdefault("thong_so", {})["can_review"] = True
        detailed.append(item)

    return AiOutcome("ok", {"criteria": detailed}, "qwen3-27b")
```

(Note: the `chunks and "qwen3-27b" or "qwen3-27b"` expression in `_list_criteria` simplifies to `"qwen3-27b"`; keep it as the literal `"qwen3-27b"` — replace that return line with `return AiOutcome("ok", {"criteria": _merge_criteria(lists)}, "qwen3-27b")`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_chunking.py tests/test_extract_rubric.py -v`
Expected: PASS (chunking 3 passed; extract_rubric 3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/services/extraction.py backend/tests/test_chunking.py backend/tests/test_extract_rubric.py
git commit -m "feat: two-step rubric extraction with structure-aware chunking"
```

---

### Task 8: Rubric router handles locator miss + extraction error

**Files:**
- Modify: `backend/routers/rubric.py:96-108`
- Test: `backend/tests/test_rubric_api.py` (extend)

**Interfaces:**
- Consumes: new locator shape (Task 6), `extract_rubric -> AiOutcome` (Task 7).

- [ ] **Step 1: Write the failing test**

First read the existing `backend/tests/test_rubric_api.py` to match its fixtures/helpers (how a package + HSMT doc is created). Then append these tests, reusing that file's existing setup helpers (adapt the helper names to those already in the file):

```python
@pytest.mark.asyncio
async def test_extract_fails_when_tcdg_not_located(client, db_session):
    # Tạo gói + HSMT KHÔNG có heading "tiêu chuẩn đánh giá"
    pkg_id = _make_package_with_hsmt(db_session, hsmt_text="Trang bìa, mục lục, không có heading TCĐG")
    r = client.post(f"/api/v1/packages/{pkg_id}/rubric")
    assert r.status_code == 422
    assert "không định vị được" in r.json()["error"].lower()
```

(`_make_package_with_hsmt` — if the file lacks such a helper, inline the package+document creation the same way the existing extract test does, but set the HSMT `extracted_text` to a JSON pages list with no TCĐG heading.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_rubric_api.py -v`
Expected: FAIL (current code returns 200 because old locator fell back to whole doc + mock)

- [ ] **Step 3: Update the `extract` endpoint**

In `backend/routers/rubric.py`, replace the `extract` function body (lines 96-108) with:

```python
@router.post("/{package_id}/rubric")
async def extract(package_id: int, db: Session = Depends(get_db)):
    """Trích xuất tiêu chí đánh giá từ HSMT bằng AI và lưu vào DB."""
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    hsmt = next((d for d in pkg.documents if d.loai == "HSMT"), None)
    if not hsmt:
        return fail("Chưa upload HSMT", 400)
    sections = locate_hsmt_sections(_pages(hsmt))
    if not sections["tcdg"]["located"]:
        return fail("Không định vị được mục Tiêu chuẩn đánh giá trong HSMT — kiểm tra lại file HSMT", 422)
    outcome = await extract_rubric(sections)
    if outcome.status == "error":
        return fail(f"Trích xuất tiêu chí thất bại: {outcome.error}", 502)
    _persist(db, package_id, outcome.data["criteria"])
    return ok(_read(db, package_id))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_rubric_api.py -v`
Expected: PASS (existing extract test still passes via mock; new 422 test passes)

- [ ] **Step 5: Commit**

```bash
git add backend/routers/rubric.py backend/tests/test_rubric_api.py
git commit -m "feat: rubric router surfaces locator miss (422) and extraction error (502)"
```

---

### Task 9: ERROR-aware sub-check evaluation

**Files:**
- Modify: `backend/services/evaluation/base.py` (`eval_one`, `evaluate_criterion`, `aggregate_subresults`)
- Test: `backend/tests/test_evaluate_criterion.py` (extend), `backend/tests/test_eval_legality.py` (verify still green)

**Interfaces:**
- Consumes: `ai_call`/`AiOutcome` (Task 4), `cot_block`/`SCALE_DEF` (Task 5), `validate_eval_verdict`/`validate_sub_verdict` (Task 3), `clamp_page_refs` (Task 2), `artifact_catalog.all_codes`.
- Produces: `evaluate_criterion(criterion, artifact_content_map, max_page: int = 0)`; sub-check `result` may now be `"ERROR"`; criterion verdict may be `"ERROR"`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_evaluate_criterion.py`:

```python
@pytest.mark.asyncio
async def test_ai_error_becomes_error_result(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)

    async def boom(*a, **k):
        return ai_client.AiOutcome("error", None, "qwen3-27b", "timeout")

    monkeypatch.setattr(base, "ai_call", boom)
    crit = {"ten": "X", "required_artifacts": ["don_du_thau"], "sub_checks": [
        {"ten": "Suy xét nội dung", "check_type": "semantic_match", "thong_so": {},
         "required_artifact": "don_du_thau", "blocking": True}]}
    subs = await base.evaluate_criterion(crit, {"don_du_thau": "nội dung đơn"})
    assert subs[0]["result"] == "ERROR"
    assert "timeout" in subs[0]["evidence"]


@pytest.mark.asyncio
async def test_artifact_outside_catalog_is_error_not_fail():
    crit = {"ten": "X", "required_artifacts": ["khong_ton_tai"], "sub_checks": [
        {"ten": "Kiểm tra", "check_type": "presence", "thong_so": {},
         "required_artifact": "khong_ton_tai", "blocking": True}]}
    subs = await base.evaluate_criterion(crit, {"khong_ton_tai": "abc"})
    assert subs[0]["result"] == "ERROR"
    assert "ngoài danh mục" in subs[0]["evidence"]


def test_aggregate_error_takes_precedence():
    crit = {"sub_checks": [{"ten": "A", "blocking": True}, {"ten": "B", "blocking": True}]}
    subs = [
        {"sub_check_ten": "A", "result": "PASS", "evidence": "", "page_ref": [], "nguon_file": "", "ai_model": ""},
        {"sub_check_ten": "B", "result": "ERROR", "evidence": "", "page_ref": [], "nguon_file": "", "ai_model": ""},
    ]
    assert base.aggregate_subresults(crit, subs)["result"] == "ERROR"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_evaluate_criterion.py -v`
Expected: FAIL (no catalog guard; `ai_call` not referenced in `base`; aggregate has no ERROR branch)

- [ ] **Step 3: Update `base.py`**

In `backend/services/evaluation/base.py`, replace the import line `from services.ai_client import ai_json` with:

```python
from services.ai_client import ai_call
from services.evaluation.checks import run_deterministic_check
from services import artifact_catalog
from services.json_utils import clamp_page_refs
from services.prompts import cot_block, SCALE_DEF
from services.ai_schemas import validate_eval_verdict, validate_sub_verdict
```

Replace `eval_one` (lines 27-49) with:

```python
async def eval_one(
    system: str, criteria: dict[str, Any], content: str, mock_key: str
) -> EvalResult:
    prompt = (
        f"Tiêu chí: {criteria.get('ten')}\n"
        f"Yêu cầu HSMT: {criteria.get('yeu_cau', '')}\n"
        f"Nội dung HSDT:\n{content[:8000]}\n\n"
        + cot_block('{"evidence":"...","result":"PASS|FAIL|PARTIAL","score":0-100,"page_ref":[...],"note":"..."}',
                    scale=SCALE_DEF)
    )
    out = await ai_call(system, prompt, mock_key=mock_key, validate=validate_eval_verdict)
    if out.status == "error":
        return EvalResult(
            criteria_ten=criteria.get("ten", ""), result="ERROR", score=0.0,
            evidence=f"AI lỗi: {out.error}", page_ref=[], note="", ai_model="",
        )
    data = out.data
    result = data.get("result", "PARTIAL")
    if result not in {"PASS", "FAIL", "PARTIAL"}:
        result = "PARTIAL"
    return EvalResult(
        criteria_ten=criteria.get("ten", ""),
        result=result,
        score=_clamp(data.get("score", 0)),
        evidence=data.get("evidence") or "Không có dẫn chứng",
        page_ref=clamp_page_refs(data.get("page_ref"), 0),
        note=data.get("note", ""),
        ai_model=out.model,
    )
```

Replace `evaluate_criterion` (lines 70-114) with:

```python
async def evaluate_criterion(
    criterion: dict[str, Any], artifact_content_map: dict[str, str], max_page: int = 0
) -> list[SubResult]:
    """Đánh giá từng sub_check của một tiêu chí, routing sang deterministic hoặc AI."""
    out: list[SubResult] = []
    valid_codes = set(artifact_catalog.all_codes())
    for sc in criterion.get("sub_checks", []):
        art = sc.get("required_artifact", "")
        if art and art not in valid_codes:
            # Mã hồ sơ AI đề xuất nằm ngoài danh mục -> cần người xử lý, KHÔNG đổ lỗi nhà thầu.
            out.append(SubResult(
                sub_check_ten=sc["ten"], result="ERROR",
                evidence=f"AI đề xuất loại hồ sơ ngoài danh mục: {art}",
                page_ref=[], nguon_file=art, ai_model="",
            ))
            continue
        if not art or art not in artifact_content_map:
            out.append(SubResult(
                sub_check_ten=sc["ten"], result="FAIL",
                evidence=f"Thiếu hồ sơ: {_label(art)}",
                page_ref=[], nguon_file=art, ai_model="",
            ))
            continue
        content = artifact_content_map[art]
        det = run_deterministic_check(sc.get("check_type", ""), content, sc.get("thong_so", {}))
        if det is not None:
            out.append(SubResult(
                sub_check_ten=sc["ten"], result=det["result"], evidence=det["evidence"],
                page_ref=det.get("page_ref") or [], nguon_file=art, ai_model="python",
            ))
            continue
        prompt = (
            f"Điểm kiểm: {sc['ten']} (loại {sc.get('check_type')})\n"
            f"Nội dung hồ sơ '{_label(art)}':\n{content[:6000]}\n\n"
            + cot_block('{"evidence":"...","result":"PASS|FAIL|PARTIAL","page_ref":[...]}', scale=SCALE_DEF)
        )
        res_out = await ai_call(_SYS_SUB, prompt, mock_key="eval_subcheck", validate=validate_sub_verdict)
        if res_out.status == "error":
            out.append(SubResult(
                sub_check_ten=sc["ten"], result="ERROR",
                evidence=f"AI lỗi: {res_out.error}", page_ref=[], nguon_file=art, ai_model="",
            ))
            continue
        data = res_out.data
        res = data.get("result", "PARTIAL")
        if res not in {"PASS", "FAIL", "PARTIAL"}:
            res = "PARTIAL"
        out.append(SubResult(
            sub_check_ten=sc["ten"], result=res,
            evidence=data.get("evidence") or "Không có dẫn chứng",
            page_ref=clamp_page_refs(data.get("page_ref"), max_page),
            nguon_file=art, ai_model=res_out.model,
        ))
    return out
```

In `aggregate_subresults` (lines 117-133), add an ERROR precedence branch. Replace the verdict-decision block:

```python
    error_present = any(r["result"] == "ERROR" for r in sub_results)
    all_pass = bool(sub_results) and all(r["result"] == "PASS" for r in sub_results)
    if error_present:
        result = "ERROR"
    elif blocking_fail:
        result = "FAIL"
    elif all_pass:
        result = "PASS"
    else:
        result = "PARTIAL"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_evaluate_criterion.py tests/test_eval_legality.py -v`
Expected: PASS (existing missing-artifact/deterministic/aggregate tests still pass; 3 new pass)

- [ ] **Step 5: Commit**

```bash
git add backend/services/evaluation/base.py backend/tests/test_evaluate_criterion.py
git commit -m "feat: surface AI errors as ERROR verdict in sub-check evaluation"
```

---

### Task 10: Thread max_page + persist ERROR through evaluation

**Files:**
- Modify: `backend/services/evaluation/legality.py:28-40`, `backend/routers/evaluation.py:69-91`
- Test: `backend/tests/test_legality_routed.py` (extend), `backend/tests/test_evaluation_routed_api.py` (verify green)

**Interfaces:**
- Consumes: `evaluate_criterion(..., max_page)` (Task 9).
- Produces: `evaluate_legality_routed(criteria, artifact_content_map, max_page: int = 0)`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_legality_routed.py`:

```python
@pytest.mark.asyncio
async def test_routed_passes_max_page(monkeypatch):
    seen = {}

    async def fake_eval(criterion, amap, max_page=0):
        seen["max_page"] = max_page
        return []

    from services.evaluation import legality as L
    monkeypatch.setattr(L, "evaluate_criterion", fake_eval)
    await L.evaluate_legality_routed(
        [{"nhom": "hop_le", "ten": "X", "sub_checks": []}], {}, max_page=12)
    assert seen["max_page"] == 12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_legality_routed.py -v`
Expected: FAIL with `TypeError: evaluate_legality_routed() got an unexpected keyword argument 'max_page'`

- [ ] **Step 3: Thread max_page**

In `backend/services/evaluation/legality.py`, replace `evaluate_legality_routed` (lines 28-40):

```python
async def evaluate_legality_routed(
    criteria: list[dict[str, Any]], artifact_content_map: dict[str, str], max_page: int = 0
) -> list[dict[str, Any]]:
    """Đánh giá tiêu chí hợp lệ theo artifact routing (chỉ nhóm hop_le)."""
    out: list[dict[str, Any]] = []
    for c in criteria:
        if c.get("nhom") != "hop_le":
            continue
        subs = await evaluate_criterion(c, artifact_content_map, max_page)
        agg = aggregate_subresults(c, subs)
        out.append({"criteria_ten": c["ten"], "result": agg["result"],
                    "score": agg["score"], "sub_results": subs})
    return out
```

In `backend/routers/evaluation.py`, compute `max_page` per vendor and pass it. Replace the loop body inside `evaluate` (lines 70-72):

```python
    for vendor in pkg.vendors:
        amap, present = _artifact_map(pkg, vendor.id)
        max_page = 0
        for d in pkg.documents:
            if d.vendor_id != vendor.id:
                continue
            for p in _pages(d):
                max_page = max(max_page, int(p.get("page", 0)))
        routed = await evaluate_legality_routed(crit_dicts, amap, max_page)
```

(The existing `db.add(models.SubCheckResult(... ket_qua=s["result"] ...))` already persists `"ERROR"` strings without change — no further edit needed there.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_legality_routed.py tests/test_evaluation_routed_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/evaluation/legality.py backend/routers/evaluation.py backend/tests/test_legality_routed.py
git commit -m "feat: thread max_page through evaluation; persist ERROR verdicts"
```

---

### Task 11: Treat ERROR as not-passed + block report export

**Files:**
- Modify: `backend/routers/reports.py` (`_rebuild_evals` `passed_legality`; guard in `generate_report`)
- Test: `backend/tests/test_reports_api.py` (extend)

**Interfaces:**
- Consumes: `SubCheckResult.ket_qua == "ERROR"` (Task 10).

- [ ] **Step 1: Write the failing test**

First read `backend/tests/test_reports_api.py` for its existing package/eval setup helpers. Then append a test that creates a package with at least one `SubCheckResult` having `ket_qua="ERROR"` (not overridden) and asserts export is blocked:

```python
def test_export_blocked_when_unresolved_error(client, db_session):
    # Dựng gói có 1 sub-check result ERROR chưa override (tái dùng helper sẵn có trong file này).
    pkg_id, sub_id = _make_package_with_subcheck(db_session)
    db_session.add(models.SubCheckResult(
        sub_check_id=sub_id, vendor_id=_vendor_id(db_session, pkg_id),
        ket_qua="ERROR", evidence="AI lỗi", page_ref=[], nguon_file="", ai_model=""))
    db_session.commit()
    r = client.post(f"/api/v1/packages/{pkg_id}/reports?loai=excel")
    assert r.status_code == 409
    assert "ai lỗi" in r.json()["error"].lower()
```

(Adapt `_make_package_with_subcheck`/`_vendor_id` to the file's existing fixtures; if absent, inline creation of package → criteria → EvaluationSubCheck → SubCheckResult following the patterns already used by other tests in that file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_reports_api.py -v`
Expected: FAIL (export currently returns 200)

- [ ] **Step 3: Add the guard and fix passed_legality**

In `backend/routers/reports.py`, add this import near the top (after `from services import reports`):

```python
from sqlalchemy import select
```

(`select` is already imported in this file — verify; if present, skip.)

At the start of `generate_report`, after the `loai` validation block (line 91), insert the export guard:

```python
    # Chặn xuất khi còn điểm kiểm AI lỗi chưa được chuyên gia xử lý.
    sub_ids = [
        s.id for c in pkg.criteria
        for s in db.scalars(select(models.EvaluationSubCheck).where(
            models.EvaluationSubCheck.criteria_id == c.id)).all()
    ]
    if sub_ids:
        n_err = db.scalar(
            select(models.SubCheckResult).where(
                models.SubCheckResult.sub_check_id.in_(sub_ids),
                models.SubCheckResult.ket_qua == "ERROR",
                models.SubCheckResult.overridden.is_(False),
            )
        )
        if n_err is not None:
            return fail("Còn điểm kiểm AI lỗi chưa xử lý — hãy điều chỉnh trước khi xuất báo cáo", 409)
```

In `_rebuild_evals`, fix `passed_legality` (it must not count ERROR as passed). Replace:

```python
            "passed_legality": bool(groups["hop_le"] + groups["nang_luc"]) and all(
                x["result"] not in ("FAIL", "ERROR")
                for x in groups["hop_le"] + groups["nang_luc"]
            ),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_reports_api.py tests/test_reports.py -v`
Expected: PASS (existing report tests still pass; new 409 test passes)

- [ ] **Step 5: Commit**

```bash
git add backend/routers/reports.py backend/tests/test_reports_api.py
git commit -m "feat: block report export on unresolved ERROR; ERROR not counted as passed"
```

---

### Task 12: Migrate artifact validation to ai_call

**Files:**
- Modify: `backend/services/artifact_classify.py`
- Test: `backend/tests/test_artifact_classify.py` (verify green; extend for error path)

**Interfaces:**
- Consumes: `ai_call`/`AiOutcome` (Task 4), `validate_validate_artifact` (Task 3), `cot_block` (Task 5).

- [ ] **Step 1: Write the failing test**

Read `backend/tests/test_artifact_classify.py` to match style, then append:

```python
@pytest.mark.asyncio
async def test_validate_artifact_real_error_returns_match_false(monkeypatch):
    from services import artifact_classify as ac
    monkeypatch.setattr(ac.settings, "ai_mock", False)

    async def boom(*a, **k):
        from services.ai_client import AiOutcome
        return AiOutcome("error", None, "qwen3-27b", "down")

    monkeypatch.setattr(ac, "ai_call", boom)
    out = await ac.validate_artifact([{"page": 1, "text": "abc"}], "don_du_thau")
    assert out["match"] is False
    assert "ai lỗi" in out["note"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_artifact_classify.py -v`
Expected: FAIL (`ac.ai_call` does not exist; module imports `ai_json`)

- [ ] **Step 3: Migrate the module**

Replace the import line in `backend/services/artifact_classify.py` (`from services.ai_client import ai_json, settings`) with:

```python
from services.ai_client import ai_call, settings
from services.prompts import cot_block
from services.ai_schemas import validate_validate_artifact
```

Replace the AI call at the end of `validate_artifact` (lines 23-27):

```python
    declared = artifact_catalog.get_artifact(declared_type)
    label = declared["label"] if declared else declared_type
    prompt = (f"Loại khai báo: {label}. Nội dung file:\n{text}\n\n"
              + cot_block('{"match":true|false,"suggested_type":"<code hoặc rỗng>","confidence":0-1,"note":"..."}'))
    out = await ai_call(_SYS, prompt, mock_key="validate_artifact", validate=validate_validate_artifact)
    if out.status == "error":
        return {"match": False, "suggested_type": "", "confidence": 0.0,
                "note": f"AI lỗi khi kiểm tra loại hồ sơ: {out.error}", "_model": out.model}
    return {**out.data, "_model": out.model}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_artifact_classify.py -v`
Expected: PASS (mock-path tests still pass; new error-path test passes)

- [ ] **Step 5: Commit**

```bash
git add backend/services/artifact_classify.py backend/tests/test_artifact_classify.py
git commit -m "feat: migrate artifact validation to ai_call with error surfacing"
```

---

### Task 13: Remove `ai_json` and dead legacy functions

**Files:**
- Modify: `backend/services/ai_client.py` (remove `ai_json`, `_mock`, mock keys `extract_criteria`/`map_hsdt`)
- Modify: `backend/services/extraction.py` (remove `extract_criteria`, `map_hsdt`, `_SYS_EXTRACT`, `_SYS_MAP`, `_join`, and the now-unused `ai_json` import)
- Delete: `backend/tests/test_extraction.py` (covers only the removed functions)
- Modify: `backend/tests/test_ai_client.py` (remove the two `ai_json` tests)

**Interfaces:** none added; this is cleanup. Confirm no production caller remains: `grep -rn "ai_json\|extract_criteria\|map_hsdt" backend --include=*.py` should show only definitions about to be deleted (no other callers).

- [ ] **Step 1: Verify no remaining callers**

Run: `cd backend && grep -rn "ai_json\|extract_criteria\|map_hsdt" --include=*.py .`
Expected: only matches in `services/ai_client.py`, `services/extraction.py`, `tests/test_ai_client.py`, `tests/test_extraction.py`. If anything else appears, STOP and migrate it first.

- [ ] **Step 2: Remove the dead code**

In `backend/services/ai_client.py`: delete the `async def ai_json(...)` function (the block starting `async def ai_json`) and the `def _mock(...)` function; delete the `"extract_criteria": {...}` and `"map_hsdt": {...}` entries from `MOCK_RESPONSES`. Add a tiny inline `_mock` replacement is NOT needed (only `ai_call` uses mock now, inline via `copy.deepcopy`).

In `backend/services/extraction.py`: delete `extract_criteria`, `map_hsdt`, `_SYS_EXTRACT`, `_SYS_MAP`, `_join`; remove `ai_json` from the import line, leaving `from services.ai_client import ai_call, AiOutcome`.

Delete the test file:

```bash
git rm backend/tests/test_extraction.py
```

In `backend/tests/test_ai_client.py`: remove both test functions (the whole file now has no `ai_json` reference). If the file becomes empty, delete it too:

```bash
git rm backend/tests/test_ai_client.py
```

- [ ] **Step 3: Run the full suite**

Run: `cd backend && pytest`
Expected: PASS (all remaining tests green; no ImportError)

- [ ] **Step 4: Commit**

```bash
git add -A backend
git commit -m "refactor: remove ai_json and dead extract_criteria/map_hsdt"
```

---

### Task 14: Frontend ERROR states + disable export

**Files:**
- Modify: `frontend/src/index.css` (add `.verdict-result-pill.ERROR`, `.source-chip.error`)
- Modify: `frontend/src/components/SubCheckTable.tsx` (`ResultPill`, `SourceChip`)
- Modify: `frontend/src/pages/Evaluation.tsx` (`ResultPill`, export buttons disabled on ERROR)
- Test: static verification only (node unavailable in this WSL env — do NOT run `npm`).

**Interfaces:** consumes `result: "ERROR"` and `ai_model: ""` from `/results` (Tasks 10–11). `SubResult`/`CriteriaBreakdown` types already type `result` as `string` — no `types.ts` change.

- [ ] **Step 1: Add CSS states**

In `frontend/src/index.css`, after line 220 (`.verdict-result-pill.default {...}`), add:

```css
.verdict-result-pill.ERROR   { background: #FBE3E1; color: var(--seal); font-weight: 700; }
```

After line 255 (`.source-chip.python {...}`), add:

```css
.source-chip.error  { border-color: var(--fail); color: var(--fail); background: var(--fail-bg); }
```

(If `--seal`/`--fail-bg` are not defined, use literal `#B23A3A` / `#FBE9E7` — verify the token names exist in `:root` first.)

- [ ] **Step 2: Update SubCheckTable**

In `frontend/src/components/SubCheckTable.tsx`, replace `ResultPill` and `SourceChip`:

```tsx
function ResultPill({ result }: { result: string }) {
  const cls = ["PASS", "FAIL", "PARTIAL", "ERROR"].includes(result) ? result : "default";
  const label = result === "ERROR" ? "AI LỖI" : result;
  return <span className={`verdict-result-pill ${cls}`}>{label}</span>;
}

function SourceChip({ model, result }: { model: string; result?: string }) {
  if (result === "ERROR") return <span className="source-chip error">AI lỗi</span>;
  if (!model) return null;
  const cls = model === "mock" ? "mock" : model.startsWith("python") ? "python" : "real";
  return <span className={`source-chip ${cls}`}>{model}</span>;
}
```

Update the "Nguồn AI" column render to pass `result` (around line 98):

```tsx
            render: (m, s) => <SourceChip model={m ?? ""} result={s.result} />,
```

- [ ] **Step 3: Update Evaluation page**

In `frontend/src/pages/Evaluation.tsx`, replace `ResultPill` (lines 9-13):

```tsx
function ResultPill({ result }: { result: string | null }) {
  const v = result ?? "—";
  const cls = ["PASS", "FAIL", "PARTIAL", "ERROR"].includes(v) ? v : "default";
  const label = v === "ERROR" ? "AI LỖI" : v;
  return <span className={`verdict-result-pill ${cls}`}>{label}</span>;
}
```

In the `Evaluation` component, after `if (!data) return null;` (line 138), compute an error flag:

```tsx
  const hasError = data.vendors.some((v) =>
    v.criteria.some((c) =>
      c.result === "ERROR" ||
      c.sub_results.some((s) => s.result === "ERROR" && !s.overridden)
    )
  );
```

Replace the two export buttons (lines 148-149) with disabled-on-error variants wrapped in a tooltip:

```tsx
          <Tooltip title={hasError ? "Còn điểm kiểm AI lỗi — hãy xử lý trước khi xuất" : ""}>
            <span style={{ display: "inline-flex", gap: 8 }}>
              <Button icon={<DownloadOutlined />} disabled={hasError} onClick={() => genReport("word")}>Xuất Word</Button>
              <Button icon={<DownloadOutlined />} disabled={hasError} onClick={() => genReport("excel")}>Xuất Excel</Button>
            </span>
          </Tooltip>
```

- [ ] **Step 4: Static verification**

Since node is unavailable, verify by reading:
- `grep -n "ERROR" frontend/src/components/SubCheckTable.tsx frontend/src/pages/Evaluation.tsx` shows the new branches.
- `grep -n "ERROR\|source-chip.error" frontend/src/index.css` shows both CSS rules.
- Confirm `Tooltip` is imported in `Evaluation.tsx` (it is, line 2) and `disabled` is a valid AntD `Button` prop.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/index.css frontend/src/components/SubCheckTable.tsx frontend/src/pages/Evaluation.tsx
git commit -m "feat: surface AI ERROR in UI and disable report export on error"
```

---

## Self-Review

**Spec coverage:**
- §2 ai_call/AiOutcome/no-silent-mock → Task 4. Legacy removal §2.4 → Task 13. ✓
- §3.1 locator section-range → Task 6. §3.2 locator-miss 422 → Task 8. §3.3 two-step + chunking → Task 7. ✓
- §4.1 CoT template → Task 5 (+ applied in Tasks 7, 9, 12). §4.2 extract_json → Task 2. §4.3 Pydantic validate → Task 3 (applied 7,9,12); catalog-out→ERROR + page_ref clamp → Tasks 9/2. ✓
- §5.1 ket_qua ERROR + aggregate + persist → Tasks 9, 10. §5.2 frontend chip/pill/disable export → Task 14. ✓
- §6 config → Task 1. ✓
- §9 rà soát reports.py (ERROR not passed) → Task 11. ✓

**Placeholder scan:** No TBD/TODO. Tasks 8 and 11 reference existing test-file helpers that the implementer must match to the actual fixtures — the test bodies and assertions are concrete; only fixture-helper names adapt to what already exists. All implementation code blocks are complete.

**Type consistency:** `AiOutcome(status, data, model, error)` used consistently (Tasks 4,7,9,12). `locate_hsmt_sections` returns `{"tcdg":{"located","pages"},...}` consistently (Tasks 6,7,8). `extract_rubric -> AiOutcome` consistent (Tasks 7,8). `evaluate_criterion(criterion, artifact_content_map, max_page=0)` / `evaluate_legality_routed(..., max_page=0)` consistent (Tasks 9,10). `result="ERROR"` string consistent across backend (Tasks 9,10,11) and frontend (Task 14).

**Scope:** P0+P1 only; P2/P3/page-picker/Alembic explicitly excluded per Global Constraints.
