# HSDT Evaluation (Legality) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đánh giá HSDT (PDF scan) cho nhóm **hợp lệ** dựa trên output decompose, dùng Qwen3.6 27B vision thay OCR.

**Architecture:** Module mới `backend/experiment/evaluate/` (prototype, KHÔNG đụng `services/`). Bốn tầng: **ingest** (mỗi trang scan → vision bóc text + phân loại hồ sơ + cờ chữ ký/dấu, MỘT lần) → **route** (mỗi nội dung kiểm tra → trang có loại hồ sơ khớp `hsdt_kiem_tra`) → **evaluate** (đối chiếu `yeu_cau`+`thong_tin_bo_sung` của decompose với text HSDT; đính ảnh khi check thị giác) → **aggregate** (roll-up mỗi tiêu chí + audit). Một cổng tiêm `vision_fn` cho cả ingest lẫn evaluate → test offline khi máy dev không có proxy.

**Tech Stack:** Python 3.11, PyMuPDF (fitz) render trang→PNG, LiteLLM proxy → Qwen3.6 27B (VL, OpenAI-compatible), pydantic v2, pytest (asyncio_mode=auto).

## Global Constraints

- Env python: `/home/hungmanh/anaconda3/bin/python3`. Chạy test từ `backend/`: `cd backend && <py> -m pytest experiment/evaluate/tests -q`.
- **Không internet trên server** → ảnh gửi model bằng **base64 inline** (`data:image/png;base64,...`), KHÔNG dùng URL. Không fetch cost-map (đã set `LITELLM_LOCAL_MODEL_COST_MAP` khi import `services.ai_client`).
- **no-silent-mock**: vision/LLM lỗi → `AiOutcome(status="error")` → verdict `"lỗi"` / tiêu chí `"cần làm rõ"`, **TUYỆT ĐỐI KHÔNG bịa** kết quả.
- KHÔNG sửa `backend/services/` và `backend/experiment/{chunking,index,decompose,extract}/`. Chỉ **import read-only**: `config.get_settings`, `services.ai_client.AiOutcome`, `services.json_utils.extract_json`, `services.artifact_catalog`.
- Tiếng Việt trong output/comment; key JSON snake_case tiếng Việt (khớp decompose).
- Phạm vi: **chỉ nhóm `hop_le`**. Các nhóm khác để bước sau.
- Ăn thẳng `decomposition.json` (schema decompose mới): tiêu chí `{nhom, ten, tien_quyet, noi_dung_can_kiem_tra:[{noi_dung_kiem_tra, hsdt_kiem_tra, yeu_cau, thong_tin_bo_sung, kieu_check, ...}]}`.
- Artifact codes hợp lệ (từ `services.artifact_catalog.all_codes()`): `don_du_thau, bao_dam_du_thau, thoa_thuan_lien_danh, tu_cach_phap_ly, bao_cao_tai_chinh, hop_dong_tuong_tu, ke_khai_nhan_su, ke_khai_thiet_bi, de_xuat_ky_thuat, catalogue_thong_so, bang_gia`.
- Vision thật cần **`ai_model` là biến thể VL trên server** — máy dev test bằng `ScriptedVision`.

---

### Task 1: schema — dataclasses + validators

**Files:**
- Create: `backend/experiment/evaluate/__init__.py` (rỗng)
- Create: `backend/experiment/evaluate/schema.py`
- Test: `backend/experiment/evaluate/tests/__init__.py` (rỗng), `backend/experiment/evaluate/tests/test_schema.py`

**Interfaces:**
- Produces:
  - `class IngestPageModel(_Base)` fields: `loai_ho_so:str="khac"`, `text:str=""`, `co_chu_ky:bool=False`, `co_dau:bool=False` — validate output vision ingest 1 trang.
  - `validate_ingest_page(d:dict)->dict`.
  - `class EvalVerdictModel(_Base)` fields: `ket_qua:str="cần làm rõ"`, `bang_chung:str=""`, `trang:list[int]=[]`, `do_tin:float=0.0`, `ghi_chu:str=""` — validate output eval 1 nội dung.
  - `validate_eval_verdict(d:dict)->dict`.
  - `@dataclass PageRecord`: `file:str`, `trang:int`, `loai_ho_so:str`, `text:str`, `co_chu_ky:bool`, `co_dau:bool`, `image:bytes=b""` (bytes chỉ trong RAM).
  - `@dataclass Verdict`: `noi_dung_kiem_tra:str`, `hsdt_kiem_tra:str`, `yeu_cau:str`, `thong_tin_bo_sung:str`, `ket_qua:str`, `bang_chung:str`, `trang:list[int]`, `do_tin:float`, `ghi_chu:str`.
  - `@dataclass CriterionEval`: `nhom:str`, `ten:str`, `tien_quyet:bool`, `ket_qua:str`, `loai:bool`, `verdicts:list[Verdict]`.
  - `@dataclass EvalResult`: `doc:str`, `criteria:list[CriterionEval]` + property `summary->{n_tieu_chi,n_dat,n_khong_dat,n_can_lam_ro,n_loai}`.
  - `KET_QUA_DAT="đạt"`, `KET_QUA_KHONG="không đạt"`, `KET_QUA_SOI="cần làm rõ"`, `KET_QUA_THIEU="thiếu hồ sơ"`, `KET_QUA_LOI="lỗi"`.
  - `result_to_json(r:EvalResult)->dict` (bỏ field `image`).

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/evaluate/tests/test_schema.py
from experiment.evaluate.schema import (
    validate_ingest_page, validate_eval_verdict, CriterionEval, Verdict,
    EvalResult, result_to_json, PageRecord,
)


def _v(ket_qua="đạt"):
    return Verdict(noi_dung_kiem_tra="Giá trị bảo lãnh", hsdt_kiem_tra="bao_dam_du_thau",
                   yeu_cau="Thỏa mãn giá trị", thong_tin_bo_sung="6.100.000 VNĐ",
                   ket_qua=ket_qua, bang_chung="ghi 6.100.000", trang=[1], do_tin=0.9, ghi_chu="")


def test_validate_ingest_page_defaults():
    out = validate_ingest_page({"loai_ho_so": "don_du_thau", "text": "abc", "field_la": "bỏ"})
    assert out["loai_ho_so"] == "don_du_thau" and out["text"] == "abc"
    assert out["co_chu_ky"] is False and out["co_dau"] is False
    assert "field_la" not in out


def test_validate_eval_verdict_defaults():
    out = validate_eval_verdict({"ket_qua": "đạt", "bang_chung": "x"})
    assert out["ket_qua"] == "đạt" and out["trang"] == [] and out["do_tin"] == 0.0


def test_result_to_json_omits_image_and_summary():
    ce = CriterionEval(nhom="hop_le", ten="Bảo đảm dự thầu", tien_quyet=True,
                       ket_qua="đạt", loai=False, verdicts=[_v("đạt")])
    r = EvalResult(doc="HSDT-A", criteria=[ce])
    d = result_to_json(r)
    assert d["doc"] == "HSDT-A"
    assert d["criteria"][0]["verdicts"][0]["ket_qua"] == "đạt"
    assert "image" not in str(d)  # bytes ảnh KHÔNG lọt vào JSON
    assert d["summary"]["n_dat"] == 1 and d["summary"]["n_tieu_chi"] == 1


def test_page_record_holds_image_bytes():
    p = PageRecord(file="a.pdf", trang=1, loai_ho_so="don_du_thau", text="x",
                   co_chu_ky=True, co_dau=False, image=b"\x89PNG")
    assert p.image == b"\x89PNG"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/evaluate/tests/test_schema.py -q`
Expected: FAIL — `ModuleNotFoundError: experiment.evaluate`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/experiment/evaluate/schema.py
"""Schema đánh giá HSDT — verdict đủ để audit (bằng chứng + trang + nguồn chuẩn HSMT)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

KET_QUA_DAT = "đạt"
KET_QUA_KHONG = "không đạt"
KET_QUA_SOI = "cần làm rõ"
KET_QUA_THIEU = "thiếu hồ sơ"
KET_QUA_LOI = "lỗi"


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


class IngestPageModel(_Base):
    loai_ho_so: str = "khac"      # mã artifact_catalog | 'khac'
    text: str = ""
    co_chu_ky: bool = False
    co_dau: bool = False


class EvalVerdictModel(_Base):
    ket_qua: str = KET_QUA_SOI
    bang_chung: str = ""
    trang: list[int] = []
    do_tin: float = 0.0
    ghi_chu: str = ""


def validate_ingest_page(d: dict[str, Any]) -> dict[str, Any]:
    return IngestPageModel(**d).model_dump()


def validate_eval_verdict(d: dict[str, Any]) -> dict[str, Any]:
    return EvalVerdictModel(**d).model_dump()


@dataclass
class PageRecord:
    file: str
    trang: int
    loai_ho_so: str
    text: str
    co_chu_ky: bool = False
    co_dau: bool = False
    image: bytes = b""            # PNG bytes — CHỈ trong RAM, không serialize


@dataclass
class Verdict:
    noi_dung_kiem_tra: str
    hsdt_kiem_tra: str
    yeu_cau: str
    thong_tin_bo_sung: str
    ket_qua: str
    bang_chung: str
    trang: list[int]
    do_tin: float
    ghi_chu: str


@dataclass
class CriterionEval:
    nhom: str
    ten: str
    tien_quyet: bool
    ket_qua: str
    loai: bool
    verdicts: list[Verdict] = field(default_factory=list)


@dataclass
class EvalResult:
    doc: str
    criteria: list[CriterionEval] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        def cnt(k: str) -> int:
            return sum(1 for c in self.criteria if c.ket_qua == k)
        return {
            "n_tieu_chi": len(self.criteria),
            "n_dat": cnt(KET_QUA_DAT),
            "n_khong_dat": cnt(KET_QUA_KHONG),
            "n_can_lam_ro": cnt(KET_QUA_SOI),
            "n_loai": sum(1 for c in self.criteria if c.loai),
        }


def result_to_json(r: EvalResult) -> dict[str, Any]:
    return {
        "doc": r.doc,
        "criteria": [asdict(c) for c in r.criteria],
        "summary": r.summary,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/evaluate/tests/test_schema.py -q`
Expected: PASS (4 passed). `PageRecord` không nằm trong `asdict` của `CriterionEval` nên `image` không lọt JSON.

- [ ] **Step 5: Commit**

```bash
cd /mnt/d/Workspace/VTX/AIBS && git add backend/experiment/evaluate/__init__.py backend/experiment/evaluate/schema.py backend/experiment/evaluate/tests/__init__.py backend/experiment/evaluate/tests/test_schema.py
git commit -m "feat(experiment): schema đánh giá HSDT (verdict + audit)"
```

---

### Task 2: vision — render PDF→ảnh + cổng vision (base64) + ScriptedVision

**Files:**
- Create: `backend/experiment/evaluate/vision.py`
- Test: `backend/experiment/evaluate/tests/test_vision.py`

**Interfaces:**
- Consumes: `services.ai_client.AiOutcome`, `services.json_utils.extract_json`, `config.get_settings`.
- Produces:
  - `pdf_to_images(data: bytes, dpi: int = 200) -> list[bytes]` — mỗi trang → PNG bytes (PyMuPDF).
  - `VisionFn = Callable[..., Awaitable[AiOutcome]]` chữ ký `(system, prompt, images: list[bytes]=(), validate=None, max_tokens=None) -> AiOutcome`.
  - `async default_vision_fn(system, prompt, images=(), validate=None, max_tokens=None) -> AiOutcome` — gọi litellm với text + image_url(base64); lỗi → status="error" (no-silent-mock); parse `extract_json` + `validate`.
  - `class ScriptedVision` — `__init__(by_match: dict[str, Any])`, `async __call__(system, prompt, images=(), validate=None, **_kw)`; khớp key đầu tiên xuất hiện trong `system+prompt`; value là dict → ok, Exception → error; ghi `self.calls: list[tuple[str, int]]` = (hay, số ảnh).

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/evaluate/tests/test_vision.py
import fitz

from experiment.evaluate.vision import pdf_to_images, ScriptedVision


def _pdf(text: str) -> bytes:
    d = fitz.open(); p = d.new_page(); p.insert_text((72, 72), text)
    return d.tobytes()


def test_pdf_to_images_one_png_per_page():
    data = _pdf("ĐƠN DỰ THẦU")
    imgs = pdf_to_images(data, dpi=120)
    assert len(imgs) == 1
    assert imgs[0][:8] == b"\x89PNG\r\n\x1a\n"   # PNG signature


async def test_scripted_vision_matches_tag_and_counts_images():
    sv = ScriptedVision({"[IN]": {"loai_ho_so": "don_du_thau", "text": "x"}})
    out = await sv("sys", "prompt [IN] here", images=[b"img1", b"img2"])
    assert out.status == "ok" and out.data["loai_ho_so"] == "don_du_thau"
    assert sv.calls[-1][1] == 2     # đếm số ảnh đã gửi


async def test_scripted_vision_error_on_exception_and_no_match():
    sv = ScriptedVision({"[BOOM]": RuntimeError("proxy down")})
    e1 = await sv("s", "x [BOOM] y")
    assert e1.status == "error" and "proxy down" in e1.error
    e2 = await sv("s", "no tag")
    assert e2.status == "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/evaluate/tests/test_vision.py -q`
Expected: FAIL — `ModuleNotFoundError: experiment.evaluate.vision`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/experiment/evaluate/vision.py
"""Render PDF scan -> ảnh, và cổng gọi Qwen VL (base64 inline, no internet).

Thật: default_vision_fn bọc litellm.completion với image_url data-URI. Test: ScriptedVision.
no-silent-mock: proxy lỗi -> AiOutcome(status='error'), KHÔNG bịa.
"""
from __future__ import annotations

import base64
from typing import Any, Awaitable, Callable

import fitz  # PyMuPDF

from config import get_settings
from services.ai_client import AiOutcome  # read-only reuse
from services.json_utils import extract_json

VisionFn = Callable[..., Awaitable[AiOutcome]]


def pdf_to_images(data: bytes, dpi: int = 200) -> list[bytes]:
    """Mỗi trang PDF -> PNG bytes (để gửi model đọc ảnh)."""
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return [page.get_pixmap(dpi=dpi).tobytes("png") for page in doc]
    finally:
        doc.close()


def _data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _content(prompt: str, images: list[bytes]) -> Any:
    if not images:
        return prompt
    parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for png in images:
        parts.append({"type": "image_url", "image_url": {"url": _data_uri(png)}})
    return parts


async def default_vision_fn(
    system: str, prompt: str, images: list[bytes] = (), validate=None, max_tokens: int | None = None,
) -> AiOutcome:
    """Gọi Qwen VL qua LiteLLM proxy (text + ảnh base64). Lỗi -> status='error'."""
    import litellm

    settings = get_settings()
    model = settings.ai_model
    if "/" not in model:
        model = f"openai/{model}"
    last_err = ""
    for _ in range(2):  # lần đầu + 1 retry
        try:
            resp = litellm.completion(
                model=model, api_base=settings.ai_base_url,
                api_key=settings.ai_api_key or "sk-no-key",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": _content(prompt, list(images))},
                ],
                temperature=settings.ai_temperature,
                max_tokens=max_tokens or settings.ai_max_tokens,
                timeout=300,
            )
            data = extract_json(resp["choices"][0]["message"]["content"])
            if validate is not None:
                data = validate(data)
            return AiOutcome(status="ok", data=data, model=settings.ai_model)
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
    return AiOutcome(status="error", data=None, model=settings.ai_model, error=last_err)


class ScriptedVision:
    """Vision kịch bản (test offline). by_match: substring-trong-(system+prompt) -> dict|Exception."""

    def __init__(self, by_match: dict[str, Any]):
        self.by_match = dict(by_match)
        self.calls: list[tuple[str, int]] = []

    async def __call__(self, system: str, prompt: str, images: list[bytes] = (),
                       validate=None, **_kw: Any) -> AiOutcome:
        hay = f"{system}\n{prompt}"
        self.calls.append((hay, len(list(images))))
        for key, data in self.by_match.items():
            if key in hay:
                if isinstance(data, Exception):
                    return AiOutcome("error", None, "scripted", error=str(data))
                if validate is not None and data is not None:
                    data = validate(data)
                return AiOutcome("ok", data, "scripted")
        return AiOutcome("error", None, "scripted", error="ScriptedVision không khớp kịch bản")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/evaluate/tests/test_vision.py -q`
Expected: PASS (3 passed). `default_vision_fn` KHÔNG bị test gọi (cần proxy) — chỉ test `pdf_to_images` + `ScriptedVision`.

- [ ] **Step 5: Commit**

```bash
cd /mnt/d/Workspace/VTX/AIBS && git add backend/experiment/evaluate/vision.py backend/experiment/evaluate/tests/test_vision.py
git commit -m "feat(experiment): render PDF->ảnh + cổng Qwen VL base64 (no internet)"
```

---

### Task 3: prompts — ingest + evaluate

**Files:**
- Create: `backend/experiment/evaluate/prompts.py`
- Test: `backend/experiment/evaluate/tests/test_prompts.py`

**Interfaces:**
- Consumes: `services.artifact_catalog`, `services.prompts.cot_block`.
- Produces:
  - `catalog_codes() -> str` (mã=nhãn, để model phân loại).
  - `SYS_INGEST: str`, `ingest_prompt() -> str` (nhúng tag `[IN]` + `cot_block`, yêu cầu {loai_ho_so, text, co_chu_ky, co_dau}).
  - `SYS_EVAL: str`, `eval_prompt(nd_item: dict, hsdt_text: str, has_image: bool) -> str` (nhúng tag `[EV:<noi_dung_kiem_tra>]`; đưa yeu_cau + thong_tin_bo_sung + hsdt_text; yêu cầu {ket_qua, bang_chung, trang, do_tin, ghi_chu}).

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/evaluate/tests/test_prompts.py
from experiment.evaluate.prompts import ingest_prompt, eval_prompt, catalog_codes


def test_ingest_prompt_has_tag_and_codes():
    p = ingest_prompt()
    assert "[IN]" in p
    assert "don_du_thau" in catalog_codes()
    assert "loai_ho_so" in p


def test_eval_prompt_carries_standard_and_tag():
    nd = {"noi_dung_kiem_tra": "Giá trị bảo lãnh", "yeu_cau": "Thỏa mãn giá trị",
          "thong_tin_bo_sung": "6.100.000 VNĐ", "kieu_check": "đối chiếu"}
    p = eval_prompt(nd, "Trang HSDT: bảo lãnh 6.100.000", has_image=False)
    assert "[EV:Giá trị bảo lãnh]" in p
    assert "6.100.000 VNĐ" in p          # chuẩn HSMT (thong_tin_bo_sung)
    assert "Thỏa mãn giá trị" in p        # yêu cầu
    assert "Trang HSDT" in p              # nội dung HSDT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/evaluate/tests/test_prompts.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/experiment/evaluate/prompts.py
"""System prompt + builder cho ingest (đọc ảnh) và evaluate (đối chiếu HSDT vs chuẩn HSMT)."""
from __future__ import annotations

from typing import Any

from services import artifact_catalog
from services.prompts import cot_block


def catalog_codes() -> str:
    return ", ".join(
        f"{c}={artifact_catalog.get_artifact(c)['label']}" for c in artifact_catalog.all_codes()
    )


SYS_INGEST = (
    "Bạn đọc ẢNH một trang hồ sơ dự thầu (HSDT) scan tiếng Việt. Hãy: (1) PHÂN LOẠI trang thuộc "
    "loại hồ sơ nào (theo danh mục mã cho sẵn; không rõ -> 'khac'); (2) BÓC toàn bộ chữ thành text "
    "(giữ số/tên/ngày chính xác, KHÔNG bịa); (3) ghi co_chu_ky (có chữ ký tay/scan không), co_dau "
    "(có con dấu đỏ/đóng dấu không). Chỉ trả JSON."
)


def ingest_prompt() -> str:
    return (
        "[IN]\n"
        f"Danh mục loại hồ sơ (code=label): {catalog_codes()}\n\n"
        + cot_block('{"loai_ho_so":"<mã hoặc khac>","text":"<toàn bộ chữ>","co_chu_ky":false,"co_dau":false}')
    )


SYS_EVAL = (
    "Bạn là chuyên gia chấm thầu. Đối chiếu NỘI DUNG HSDT của nhà thầu với CHUẨN của HSMT để kết "
    "luận. ket_qua: 'đạt' nếu HSDT thỏa mãn; 'không đạt' nếu vi phạm/không thỏa; 'cần làm rõ' nếu "
    "không đủ căn cứ. bang_chung: TRÍCH nguyên văn phần HSDT làm căn cứ (KHÔNG bịa); trang: số "
    "trang HSDT chứa căn cứ; do_tin: 0-1. Chỉ trả JSON."
)


def eval_prompt(nd_item: dict[str, Any], hsdt_text: str, has_image: bool) -> str:
    anh = "\n(KÈM ẢNH trang HSDT bên dưới — soi chữ ký/đóng dấu trực tiếp trên ảnh.)" if has_image else ""
    return (
        f"[EV:{nd_item.get('noi_dung_kiem_tra', '')}]\n"
        f"NỘI DUNG KIỂM TRA: {nd_item.get('noi_dung_kiem_tra', '')}\n"
        f"YÊU CẦU (theo HSMT): {nd_item.get('yeu_cau', '')}\n"
        f"CHUẨN HSMT (thông tin bổ sung): {nd_item.get('thong_tin_bo_sung', '') or '(không có)'}\n"
        f"KIỂU CHECK: {nd_item.get('kieu_check', '')}\n\n"
        f"NỘI DUNG HSDT (đã bóc từ ảnh):\n{hsdt_text[:6000]}{anh}\n\n"
        + cot_block('{"ket_qua":"đạt|không đạt|cần làm rõ","bang_chung":"<trích HSDT>","trang":[...],"do_tin":0.0,"ghi_chu":""}')
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/evaluate/tests/test_prompts.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /mnt/d/Workspace/VTX/AIBS && git add backend/experiment/evaluate/prompts.py backend/experiment/evaluate/tests/test_prompts.py
git commit -m "feat(experiment): prompts ingest + evaluate HSDT"
```

---

### Task 4: ingest — mỗi trang scan → PageRecord (vision, một lần)

**Files:**
- Create: `backend/experiment/evaluate/ingest.py`
- Test: `backend/experiment/evaluate/tests/test_ingest.py`

**Interfaces:**
- Consumes: `pdf_to_images` (Task 2), `VisionFn` (Task 2), `SYS_INGEST/ingest_prompt` (Task 3), `PageRecord/validate_ingest_page` (Task 1).
- Produces:
  - `async ingest_hsdt(files: list[tuple[str, bytes]], vision_fn: VisionFn, dpi: int = 200) -> list[PageRecord]` — với mỗi (tên_file, data): render trang→ảnh; mỗi ảnh gọi `vision_fn(SYS_INGEST, ingest_prompt(), images=[png], validate=validate_ingest_page)`; lỗi vision 1 trang → `PageRecord(loai_ho_so="khac", text="", ...)` (giữ ảnh, không bịa). Giữ `image=png` trong record.

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/evaluate/tests/test_ingest.py
import fitz

from experiment.evaluate.ingest import ingest_hsdt
from experiment.evaluate.vision import ScriptedVision


def _pdf(text: str) -> bytes:
    d = fitz.open(); p = d.new_page(); p.insert_text((72, 72), text)
    return d.tobytes()


async def test_ingest_transcribes_and_classifies_each_page():
    vision = ScriptedVision({"[IN]": {"loai_ho_so": "don_du_thau", "text": "Đơn dự thầu ...",
                                      "co_chu_ky": True, "co_dau": True}})
    pages = await ingest_hsdt([("don.pdf", _pdf("Đơn dự thầu"))], vision, dpi=100)
    assert len(pages) == 1
    p = pages[0]
    assert p.file == "don.pdf" and p.trang == 1
    assert p.loai_ho_so == "don_du_thau" and p.co_chu_ky is True
    assert p.image and p.image[:4] == b"\x89PNG"     # ảnh được giữ để evaluate soi thị giác


async def test_ingest_vision_error_keeps_page_no_fabrication():
    vision = ScriptedVision({"[IN]": RuntimeError("proxy down")})
    pages = await ingest_hsdt([("x.pdf", _pdf("abc"))], vision, dpi=100)
    assert len(pages) == 1
    assert pages[0].loai_ho_so == "khac" and pages[0].text == ""   # lỗi -> KHÔNG bịa
    assert pages[0].image  # vẫn giữ ảnh để người soi
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/evaluate/tests/test_ingest.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/experiment/evaluate/ingest.py
"""Tầng A — ingest HSDT scan: mỗi trang -> vision bóc text + phân loại + cờ thị giác (MỘT lần)."""
from __future__ import annotations

import logging

from experiment.evaluate.prompts import SYS_INGEST, ingest_prompt
from experiment.evaluate.schema import PageRecord, validate_ingest_page
from experiment.evaluate.vision import VisionFn, pdf_to_images

log = logging.getLogger("experiment.evaluate")


async def ingest_hsdt(
    files: list[tuple[str, bytes]], vision_fn: VisionFn, dpi: int = 200
) -> list[PageRecord]:
    """(tên_file, data pdf) -> danh sách PageRecord (giữ ảnh PNG để tầng evaluate soi thị giác)."""
    records: list[PageRecord] = []
    for name, data in files:
        images = pdf_to_images(data, dpi=dpi)
        log.info("[ingest] %s: %d trang", name, len(images))
        for i, png in enumerate(images, 1):
            out = await vision_fn(SYS_INGEST, ingest_prompt(), images=[png],
                                  validate=validate_ingest_page)
            if out.status == "ok":
                d = out.data
                rec = PageRecord(file=name, trang=i, loai_ho_so=d.get("loai_ho_so", "khac"),
                                 text=d.get("text", ""), co_chu_ky=bool(d.get("co_chu_ky")),
                                 co_dau=bool(d.get("co_dau")), image=png)
            else:
                log.warning("[ingest] %s tr%d lỗi vision: %s", name, i, out.error)
                rec = PageRecord(file=name, trang=i, loai_ho_so="khac", text="",
                                 co_chu_ky=False, co_dau=False, image=png)
            records.append(rec)
    return records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/evaluate/tests/test_ingest.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /mnt/d/Workspace/VTX/AIBS && git add backend/experiment/evaluate/ingest.py backend/experiment/evaluate/tests/test_ingest.py
git commit -m "feat(experiment): ingest HSDT scan -> PageRecord (vision một lần)"
```

---

### Task 5: route — chọn trang theo `hsdt_kiem_tra`

**Files:**
- Create: `backend/experiment/evaluate/route.py`
- Test: `backend/experiment/evaluate/tests/test_route.py`

**Interfaces:**
- Consumes: `PageRecord` (Task 1).
- Produces:
  - `route_pages(pages: list[PageRecord], hsdt_kiem_tra: str) -> list[PageRecord]` — lọc trang có `loai_ho_so == hsdt_kiem_tra` (so khớp sau khi `.strip().lower()`); rỗng nếu không loại nào khớp.
  - `pages_text(pages: list[PageRecord]) -> str` — nối `"[Trang {trang}] {text}"`.
  - `has_visual_check(kieu_check: str) -> bool` — True nếu chuẩn hoá chứa "chu ky" / "dau" / "con dau" (đ->d, bỏ dấu).

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/evaluate/tests/test_route.py
from experiment.evaluate.route import route_pages, pages_text, has_visual_check
from experiment.evaluate.schema import PageRecord


def _p(trang, loai, text):
    return PageRecord(file="f.pdf", trang=trang, loai_ho_so=loai, text=text)


def test_route_selects_matching_doc_type():
    pages = [_p(1, "don_du_thau", "đơn"), _p(2, "bao_dam_du_thau", "bảo lãnh 6tr"), _p(3, "khac", "x")]
    got = route_pages(pages, "bao_dam_du_thau")
    assert [p.trang for p in got] == [2]
    assert route_pages(pages, "khong_co") == []      # không loại nào khớp -> rỗng (thiếu hồ sơ)


def test_pages_text_joins_with_page_markers():
    txt = pages_text([_p(2, "bao_dam_du_thau", "bảo lãnh 6tr")])
    assert "[Trang 2]" in txt and "bảo lãnh 6tr" in txt


def test_has_visual_check():
    assert has_visual_check("chữ ký & đóng dấu") is True
    assert has_visual_check("con dấu") is True
    assert has_visual_check("đối chiếu") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/evaluate/tests/test_route.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/experiment/evaluate/route.py
"""Tầng B — route nội dung kiểm tra sang trang HSDT có loại hồ sơ khớp hsdt_kiem_tra."""
from __future__ import annotations

import unicodedata

from experiment.evaluate.schema import PageRecord

_VISUAL = ("chu ky", "dau")  # chữ ký / con dấu / đóng dấu


def _norm(s: str) -> str:
    s = (s or "").lower().strip().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def route_pages(pages: list[PageRecord], hsdt_kiem_tra: str) -> list[PageRecord]:
    key = _norm(hsdt_kiem_tra)
    return [p for p in pages if _norm(p.loai_ho_so) == key] if key else []


def pages_text(pages: list[PageRecord]) -> str:
    return "\n".join(f"[Trang {p.trang}] {p.text}" for p in pages)


def has_visual_check(kieu_check: str) -> bool:
    n = _norm(kieu_check)
    return any(v in n for v in _VISUAL)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/evaluate/tests/test_route.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /mnt/d/Workspace/VTX/AIBS && git add backend/experiment/evaluate/route.py backend/experiment/evaluate/tests/test_route.py
git commit -m "feat(experiment): route nội dung kiểm tra -> trang HSDT (theo loại hồ sơ)"
```

---

### Task 6: evaluate — verdict mỗi nội dung + roll-up tiêu chí

**Files:**
- Create: `backend/experiment/evaluate/evaluate.py`
- Test: `backend/experiment/evaluate/tests/test_evaluate.py`

**Interfaces:**
- Consumes: `route_pages/pages_text/has_visual_check` (Task 5), `SYS_EVAL/eval_prompt` (Task 3), `validate_eval_verdict` (Task 1), `Verdict/CriterionEval` + hằng `KET_QUA_*` (Task 1), `VisionFn` (Task 2).
- Produces:
  - `async eval_noi_dung(nd_item: dict, pages: list[PageRecord], vision_fn: VisionFn) -> Verdict` — route theo `hsdt_kiem_tra`; rỗng → `KET_QUA_THIEU`; có trang → gọi `vision_fn(SYS_EVAL, eval_prompt(...), images=<ảnh nếu has_visual_check>, validate=validate_eval_verdict)`; lỗi → `KET_QUA_LOI`. ket_qua ngoài {đạt,không đạt,cần làm rõ} → `KET_QUA_SOI`.
  - `async evaluate_criterion(crit: dict, pages: list[PageRecord], vision_fn: VisionFn) -> CriterionEval` — lặp `noi_dung_can_kiem_tra`; roll-up: có "không đạt" → tiêu chí "không đạt" (`loai = tien_quyet`); còn lại có {cần làm rõ, thiếu hồ sơ, lỗi} → "cần làm rõ"; tất cả "đạt" → "đạt".

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/evaluate/tests/test_evaluate.py
from experiment.evaluate.evaluate import eval_noi_dung, evaluate_criterion
from experiment.evaluate.vision import ScriptedVision
from experiment.evaluate.schema import PageRecord, KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_THIEU


def _page(loai, text, image=b"\x89PNG", co_chu_ky=False):
    return PageRecord(file="f.pdf", trang=1, loai_ho_so=loai, text=text, co_chu_ky=co_chu_ky, image=image)


def _nd(noi_dung, hsdt, kieu="đối chiếu"):
    return {"noi_dung_kiem_tra": noi_dung, "hsdt_kiem_tra": hsdt, "yeu_cau": "theo HSMT",
            "thong_tin_bo_sung": "6.100.000 VNĐ", "kieu_check": kieu}


async def test_eval_noi_dung_missing_doc_is_thieu_ho_so():
    v = await eval_noi_dung(_nd("Giá trị bảo lãnh", "bao_dam_du_thau"),
                            [_page("don_du_thau", "đơn")], ScriptedVision({}))
    assert v.ket_qua == KET_QUA_THIEU     # không có trang bảo đảm dự thầu


async def test_eval_noi_dung_pass_from_text():
    vision = ScriptedVision({"[EV:Giá trị bảo lãnh]":
                             {"ket_qua": "đạt", "bang_chung": "6.100.000", "trang": [1], "do_tin": 0.9}})
    v = await eval_noi_dung(_nd("Giá trị bảo lãnh", "bao_dam_du_thau"),
                            [_page("bao_dam_du_thau", "bảo lãnh 6.100.000 VNĐ")], vision)
    assert v.ket_qua == KET_QUA_DAT and v.trang == [1]
    assert v.thong_tin_bo_sung == "6.100.000 VNĐ"   # chuẩn HSMT lưu vào verdict để audit
    assert vision.calls[-1][1] == 0                 # check đối chiếu -> KHÔNG đính ảnh


async def test_eval_noi_dung_visual_check_attaches_image():
    vision = ScriptedVision({"[EV:Chữ ký đóng dấu]":
                             {"ket_qua": "đạt", "bang_chung": "có chữ ký", "trang": [1], "do_tin": 0.8}})
    await eval_noi_dung(_nd("Chữ ký đóng dấu", "bao_dam_du_thau", kieu="chữ ký & đóng dấu"),
                        [_page("bao_dam_du_thau", "thư bảo lãnh", co_chu_ky=True)], vision)
    assert vision.calls[-1][1] == 1                 # check thị giác -> đính 1 ảnh


async def test_criterion_rollup_blocking_fail_marks_loai():
    crit = {"nhom": "hop_le", "ten": "Bảo đảm dự thầu", "tien_quyet": True,
            "noi_dung_can_kiem_tra": [_nd("Giá trị bảo lãnh", "bao_dam_du_thau")]}
    vision = ScriptedVision({"[EV:Giá trị bảo lãnh]":
                             {"ket_qua": "không đạt", "bang_chung": "3 triệu < 6.1tr", "trang": [1]}})
    ce = await evaluate_criterion(crit, [_page("bao_dam_du_thau", "bảo lãnh 3.000.000")], vision)
    assert ce.ket_qua == KET_QUA_KHONG and ce.loai is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/evaluate/tests/test_evaluate.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/experiment/evaluate/evaluate.py
"""Tầng C+D — đánh giá từng nội dung (đối chiếu HSDT vs chuẩn HSMT) + roll-up tiêu chí."""
from __future__ import annotations

import logging
from typing import Any

from experiment.evaluate.prompts import SYS_EVAL, eval_prompt
from experiment.evaluate.route import has_visual_check, pages_text, route_pages
from experiment.evaluate.schema import (
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_LOI, KET_QUA_SOI, KET_QUA_THIEU,
    CriterionEval, PageRecord, Verdict, validate_eval_verdict,
)
from experiment.evaluate.vision import VisionFn

log = logging.getLogger("experiment.evaluate")
_KET_QUA_HOP_LE = {KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_SOI}
_EVAL_MAX_TOKENS = 4096


def _verdict(nd: dict[str, Any], ket_qua: str, bang_chung: str = "",
             trang: list[int] | None = None, do_tin: float = 0.0, ghi_chu: str = "") -> Verdict:
    return Verdict(
        noi_dung_kiem_tra=nd.get("noi_dung_kiem_tra", ""), hsdt_kiem_tra=nd.get("hsdt_kiem_tra", ""),
        yeu_cau=nd.get("yeu_cau", ""), thong_tin_bo_sung=nd.get("thong_tin_bo_sung", ""),
        ket_qua=ket_qua, bang_chung=bang_chung, trang=trang or [], do_tin=do_tin, ghi_chu=ghi_chu,
    )


async def eval_noi_dung(nd: dict[str, Any], pages: list[PageRecord], vision_fn: VisionFn) -> Verdict:
    """1 nội dung kiểm tra -> verdict (route + đối chiếu; đính ảnh nếu check thị giác)."""
    matched = route_pages(pages, nd.get("hsdt_kiem_tra", ""))
    if not matched:
        return _verdict(nd, KET_QUA_THIEU, bang_chung=f"HSDT không có: {nd.get('hsdt_kiem_tra', '')}",
                        ghi_chu="thiếu hồ sơ tương ứng")
    visual = has_visual_check(nd.get("kieu_check", ""))
    images = [p.image for p in matched if p.image] if visual else []
    out = await vision_fn(SYS_EVAL, eval_prompt(nd, pages_text(matched), has_image=bool(images)),
                          images=images, validate=validate_eval_verdict, max_tokens=_EVAL_MAX_TOKENS)
    if out.status == "error":
        return _verdict(nd, KET_QUA_LOI, bang_chung=f"AI lỗi: {out.error}", ghi_chu="cần soi lại")
    d = out.data
    ket_qua = d.get("ket_qua", KET_QUA_SOI)
    if ket_qua not in _KET_QUA_HOP_LE:
        ket_qua = KET_QUA_SOI
    return _verdict(nd, ket_qua, bang_chung=d.get("bang_chung", ""),
                    trang=[int(t) for t in d.get("trang", []) if str(t).isdigit()],
                    do_tin=float(d.get("do_tin", 0.0) or 0.0), ghi_chu=d.get("ghi_chu", ""))


async def evaluate_criterion(crit: dict[str, Any], pages: list[PageRecord],
                             vision_fn: VisionFn) -> CriterionEval:
    """Đánh giá mọi nội dung của 1 tiêu chí + roll-up. tien_quyet + không đạt -> loại."""
    ten = crit.get("ten", "")
    log.info("  [eval] %s", ten)
    verdicts: list[Verdict] = []
    for nd in crit.get("noi_dung_can_kiem_tra", []):
        verdicts.append(await eval_noi_dung(nd, pages, vision_fn))
    kq = {v.ket_qua for v in verdicts}
    if KET_QUA_KHONG in kq:
        ket_qua = KET_QUA_KHONG
    elif kq & {KET_QUA_SOI, KET_QUA_THIEU, KET_QUA_LOI}:
        ket_qua = KET_QUA_SOI
    elif verdicts and kq == {KET_QUA_DAT}:
        ket_qua = KET_QUA_DAT
    else:
        ket_qua = KET_QUA_SOI
    loai = ket_qua == KET_QUA_KHONG and bool(crit.get("tien_quyet"))
    return CriterionEval(nhom=crit.get("nhom", "hop_le"), ten=ten, tien_quyet=bool(crit.get("tien_quyet")),
                         ket_qua=ket_qua, loai=loai, verdicts=verdicts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/evaluate/tests/test_evaluate.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd /mnt/d/Workspace/VTX/AIBS && git add backend/experiment/evaluate/evaluate.py backend/experiment/evaluate/tests/test_evaluate.py
git commit -m "feat(experiment): verdict mỗi nội dung + roll-up tiêu chí HSDT"
```

---

### Task 7: run_evaluate — CLI + e2e (decomposition.json + HSDT → evaluation.json/.md)

**Files:**
- Create: `backend/experiment/evaluate/run_evaluate.py`
- Test: `backend/experiment/evaluate/tests/test_run_e2e.py`

**Interfaces:**
- Consumes: `ingest_hsdt` (Task 4), `evaluate_criterion` (Task 6), `EvalResult/result_to_json` (Task 1), `default_vision_fn` (Task 2).
- Produces:
  - `async run(decomposition_path, hsdt_files: list[tuple[str,bytes]], out_dir, doc: str="HSDT", vision_fn=None) -> dict` — đọc decomposition.json; gom tiêu chí `nhom=="hop_le"` từ mọi group; `ingest_hsdt` một lần; `evaluate_criterion` mỗi tiêu chí; ghi `evaluation.json` + `evaluation.md`; trả metrics = summary. `vision_fn=None` → `default_vision_fn` (cần proxy).
  - `main(argv)` — args `--decomp`, `--hsdt` (nhiều file pdf), `--out`, `--doc`; no-silent-mock: lỗi → in stderr + return 2.

- [ ] **Step 1: Write the failing test**

```python
# backend/experiment/evaluate/tests/test_run_e2e.py
import json
import fitz

from experiment.evaluate.run_evaluate import run
from experiment.evaluate.vision import ScriptedVision


def _pdf(text):
    d = fitz.open(); p = d.new_page(); p.insert_text((72, 72), text)
    return d.tobytes()


async def test_run_e2e_legality(tmp_path):
    decomp = {"doc": "E-HSMT", "groups": [{"group": "hop_le", "muc": "Mục 1", "criteria": [{
        "nhom": "hop_le", "ten": "Bảo đảm dự thầu", "tien_quyet": True,
        "noi_dung_can_kiem_tra": [{"noi_dung_kiem_tra": "Giá trị bảo lãnh",
            "hsdt_kiem_tra": "bao_dam_du_thau", "yeu_cau": "theo HSMT",
            "thong_tin_bo_sung": "6.100.000 VNĐ", "kieu_check": "đối chiếu"}]}]},
        {"group": "tai_chinh", "criteria": [{"nhom": "tai_chinh", "ten": "Giá", "noi_dung_can_kiem_tra": []}]}]}
    dp = tmp_path / "decomposition.json"
    dp.write_text(json.dumps(decomp, ensure_ascii=False), encoding="utf-8")

    vision = ScriptedVision({
        "[IN]": {"loai_ho_so": "bao_dam_du_thau", "text": "Thư bảo lãnh 6.100.000 VNĐ", "co_dau": True},
        "[EV:Giá trị bảo lãnh]": {"ket_qua": "đạt", "bang_chung": "6.100.000", "trang": [1], "do_tin": 0.9},
    })
    out = tmp_path / "out"
    metrics = await run(str(dp), [("bao_lanh.pdf", _pdf("bảo lãnh"))], str(out),
                        doc="HSDT-NhaThauA", vision_fn=vision)

    assert metrics["n_tieu_chi"] == 1 and metrics["n_dat"] == 1   # CHỈ nhóm hop_le
    data = json.loads((out / "evaluation.json").read_text(encoding="utf-8"))
    assert data["doc"] == "HSDT-NhaThauA"
    assert data["criteria"][0]["ket_qua"] == "đạt"
    assert "image" not in str(data)                              # ảnh không lọt JSON
    assert (out / "evaluation.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/evaluate/tests/test_run_e2e.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/experiment/evaluate/run_evaluate.py
"""CLI: decomposition.json + HSDT (pdf scan) -> evaluation.json/.md (nhóm hợp lệ)."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from experiment.evaluate.evaluate import evaluate_criterion
from experiment.evaluate.ingest import ingest_hsdt
from experiment.evaluate.schema import EvalResult, result_to_json
from experiment.evaluate.vision import default_vision_fn

log = logging.getLogger("experiment.evaluate")


def _legality_criteria(decomp: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for g in decomp.get("groups", []):
        for c in g.get("criteria", []):
            if c.get("nhom") == "hop_le" or g.get("group") == "hop_le":
                out.append(c)
    return out


def _to_markdown(r: EvalResult) -> str:
    lines = [f"# Đánh giá HSDT (hợp lệ) — {r.doc}", "", f"Tổng: {r.summary}", ""]
    for c in r.criteria:
        flag = " ⛔LOẠI" if c.loai else ""
        lines.append(f"## {c.ten} — **{c.ket_qua}**{flag}")
        for v in c.verdicts:
            lines.append(f"- {v.noi_dung_kiem_tra} (HSDT:{v.hsdt_kiem_tra}) → **{v.ket_qua}** "
                         f"(tin {v.do_tin})")
            lines.append(f"    · chuẩn HSMT: {v.thong_tin_bo_sung or '(không có)'}")
            lines.append(f"    · bằng chứng HSDT [tr {v.trang}]: {v.bang_chung}")
        lines.append("")
    return "\n".join(lines)


async def run(decomposition_path: str, hsdt_files: list[tuple[str, bytes]], out_dir: str,
              doc: str = "HSDT", vision_fn: Any | None = None) -> dict[str, Any]:
    vision_fn = vision_fn or default_vision_fn
    decomp = json.loads(Path(decomposition_path).read_text(encoding="utf-8"))
    criteria = _legality_criteria(decomp)
    log.info("[run] %d tiêu chí hợp lệ, %d file HSDT", len(criteria), len(hsdt_files))

    pages = await ingest_hsdt(hsdt_files, vision_fn)
    result = EvalResult(doc=doc)
    for c in criteria:
        result.criteria.append(await evaluate_criterion(c, pages, vision_fn))

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "evaluation.json").write_text(
        json.dumps(result_to_json(result), ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "evaluation.md").write_text(_to_markdown(result), encoding="utf-8")
    return {"doc": result.doc, **result.summary}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Đánh giá HSDT nhóm hợp lệ")
    ap.add_argument("--decomp", required=True, help="decomposition.json")
    ap.add_argument("--hsdt", nargs="+", required=True, help="các file HSDT .pdf (scan)")
    ap.add_argument("--out", default="out")
    ap.add_argument("--doc", default="HSDT")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(message)s", stream=sys.stderr)
    files = [(Path(p).name, Path(p).read_bytes()) for p in args.hsdt]
    try:
        metrics = asyncio.run(run(args.decomp, files, args.out, doc=args.doc))
    except Exception as exc:  # no-silent-mock
        print(f"[run_evaluate] LỖI: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("  Chế độ thật cần LiteLLM proxy phục vụ model VL (đọc ảnh).", file=sys.stderr)
        return 2
    print(json.dumps(metrics, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment/evaluate/tests -q`
Expected: PASS (toàn bộ evaluate/tests). Kiểm cả suite: `cd backend && /home/hungmanh/anaconda3/bin/python3 -m pytest experiment -q` → không hồi quy.

- [ ] **Step 5: Commit**

```bash
cd /mnt/d/Workspace/VTX/AIBS && git add backend/experiment/evaluate/run_evaluate.py backend/experiment/evaluate/tests/test_run_e2e.py
git commit -m "feat(experiment): CLI đánh giá HSDT hợp lệ (decomposition + scan -> evaluation)"
```

---

## Nghiệm thu khi proxy VL bật (server, tài liệu — không chạy ở máy dev)

1. Xác minh `ai_model` là biến thể VL: gửi 1 ảnh trang thử qua `default_vision_fn` → trả JSON `{loai_ho_so,text,...}` không lỗi.
2. `cd backend && python -m experiment.evaluate.run_evaluate --decomp experiment/out/decomposition.json --hsdt <đường_dẫn>/bao_lanh.pdf <...>/don.pdf --out experiment/out --doc "HSDT-NhaThauA"` → `evaluation.md`:
   - trang bảo lãnh phân loại `bao_dam_du_thau`, text bóc đúng số `6.100.000`;
   - tiêu chí "Bảo đảm dự thầu" đối chiếu chuẩn HSMT (6.100.000 / ≥120 ngày / Vietsovpetro) → đạt/không đạt có bằng chứng + trang;
   - check "chữ ký & đóng dấu" có đính ảnh (log `[eval]`), verdict dựa trên soi ảnh.
3. Proxy tắt / model không đọc ảnh → verdict `"lỗi"` + `run` return 2, KHÔNG bịa.

## Ghi chú tích hợp (ngoài phạm vi plan này)
- Sau nghiệm thu hợp lệ → nhân ra `nang_luc/ky_thuat/tai_chinh` (đặc thù bảng/spec).
- `hsdt_kiem_tra` của decompose nên chuẩn hoá về mã `artifact_catalog` (hiện route so khớp chuẩn hoá chuỗi; nếu decompose trả nhãn tự nhiên, bổ sung map nhãn→mã ở tầng route).
