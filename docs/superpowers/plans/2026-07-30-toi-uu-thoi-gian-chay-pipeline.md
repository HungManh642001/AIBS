# Tối ưu thời gian chạy pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bỏ nút thắt "mỗi lúc chỉ một request tới LLM" — async hoá call LLM rồi song song hoá năm vòng lặp trong phạm vi một nhà thầu, để vLLM trên H100 được chạy nhiều sequence đồng thời.

**Architecture:** Tầng 1 bọc lời gọi `litellm` đồng bộ bằng `asyncio.to_thread` và đặt MỘT semaphore toàn cục (trần đọc từ env) cho mọi call LLM. Tầng 2 thay năm vòng lặp `await` tuần tự bằng `asyncio.gather` — `gather` giữ nguyên thứ tự kết quả nên verdict và roll-up không đổi. Semaphore toàn cục giữ tổng số request đang bay trong tầm kiểm soát dù các `gather` lồng nhau.

**Tech Stack:** Python 3.11 + asyncio, FastAPI, SQLAlchemy, PyMuPDF (fitz), litellm → LiteLLM proxy → vLLM/Qwen3-27B trên H100. Test: pytest (`asyncio_mode = auto`), không cần proxy.

**Spec:** `docs/superpowers/specs/2026-07-30-toi-uu-thoi-gian-chay-pipeline-design.md`

## Global Constraints

- Thư mục làm việc mọi lệnh backend: `backend/`. Chạy test: `cd backend && python -m pytest <path> -q`.
- **Baseline (đo tại commit gốc của plan):** `cd backend && python -m pytest -q` → **185 passed, 0 failed** (`pytest.ini` đặt `testpaths = tests`). `cd backend && python -m pytest experiment/evaluate/tests -q` → **304 passed, 5 failed**; 5 test đỏ đó có từ trước, KHÔNG liên quan, không được sửa và không được tăng.
- Quy ước code (CLAUDE.md): Python snake_case, **type hints bắt buộc**, PEP 8. **Tiếng Việt trong comment/docstring, tiếng Anh trong tên code.**
- **KHÔNG chạm DB từ thread.** `asyncio.to_thread` chỉ được bọc đúng lời gọi HTTP tới LLM. Mọi thao tác cache (`CachedVision.get/put`, `PageCache.get/put`) phải ở lại thread của event loop — chúng dùng chung `Session` của router, mà SQLAlchemy `Session` không an toàn đa luồng.
- **KHÔNG gọi PyMuPDF (`fitz`) từ coroutine chạy song song hay từ thread.** Đối tượng `fitz` không an toàn đa luồng.
- **Trần semaphore phải ≤ 32** — `asyncio.to_thread` dùng executor mặc định `max_workers = min(32, cpu+4)`; đặt cao hơn thì thread pool thành nút thắt ẩn.
- **`gather` phải giữ NGUYÊN thứ tự kết quả.** Roll-up tiêu chí phụ thuộc thứ tự verdict; đảo thứ tự là đổi kết quả chấm.
- **Giữ nguyên hình dạng hai thứ mà test hiện có bám vào:** `ai_client._litellm_completion` phải vẫn là **hàm đồng bộ** cùng tên (`tests/test_ai_call.py` monkeypatch nó; `tests/test_ai_determinism.py` gọi thẳng nó đồng bộ), và `import litellm` phải nằm **bên trong** thân hàm đồng bộ (`test_ai_determinism.py` thay `sys.modules["litellm"]`).
- **no-silent-mock:** lỗi AI → `AiOutcome(status='error')`, không bịa dữ liệu.
- Commit tiếng Việt, dạng `perf(<scope>): <mô tả>` / `feat(<scope>): <mô tả>`.

## File Structure

| File | Trách nhiệm | Task |
|---|---|---|
| `backend/services/llm_gate.py` | **Mới.** Semaphore toàn cục theo event loop, trần từ config | 1 |
| `backend/config.py` | Thêm `ai_song_song` | 1 |
| `backend/services/ai_client.py` | `ai_call` gọi LLM qua `to_thread` + gate | 1 |
| `backend/experiment/evaluate/vision.py` | `default_vision_fn` qua `to_thread` + gate | 1 |
| `backend/tests/test_llm_gate.py` | **Mới.** Test trần đồng thời + per-loop | 1 |
| `backend/experiment/evaluate/tests/dong_thoi.py` | **Mới.** Helper đo đồng thời, dùng lại ở Task 3-5 | 2 |
| `backend/experiment/evaluate/ingest.py` | `_doc_file` hai pha: render trước, gather sau | 2 |
| `backend/experiment/evaluate/evaluate.py` | `evaluate_criterion` gather theo nội dung | 3 |
| `backend/experiment/evaluate/pipeline.py` | `evaluate_hsdt` gather theo tiêu chí | 4 |
| `backend/experiment/evaluate/rules/registry.py` | `dispatch_standing` gather theo luật | 4 |
| `backend/experiment/evaluate/rules/lien_danh_phan_cong.py` | gather theo chunk bảng giá | 5 |

---

### Task 1: Async hoá call LLM + semaphore toàn cục

**Files:**
- Create: `backend/services/llm_gate.py`, `backend/tests/test_llm_gate.py`
- Modify: `backend/config.py` (khối `Settings`), `backend/services/ai_client.py:73-105` (`ai_call`), `backend/experiment/evaluate/vision.py:50-91` (`default_vision_fn`)

**Interfaces:**
- Produces: `services.llm_gate.cong() -> asyncio.Semaphore` — semaphore của event loop đang chạy; `Settings.ai_song_song: int` (env `ABES_AI_SONG_SONG`, mặc định 4).
- Consumes: `config.get_settings()`.

**Bối cảnh (đọc trước khi sửa):** `services/ai_client.py:43` và `experiment/evaluate/vision.py:70` đều gọi `litellm.completion(...)` — API **đồng bộ** — bên trong `async def`. Nó chẹn event loop, nên `asyncio.gather` ở `experiment/decompose/workflow.py:494` và `Semaphore` ở `:118` hiện **không tạo ra song song nào**. Bằng chứng đo được: log decompose ghi 7 need "song song" tại `+271s` rồi trả về rải rác `+361 → +406s`. Task này là điều kiện cần cho toàn bộ các task sau.

- [ ] **Step 1: Viết test thất bại cho gate**

Tạo `backend/tests/test_llm_gate.py`:

```python
"""Trần song song cho MỌI call LLM — một cổng chung, tạo theo event loop đang chạy."""
import asyncio

import config
from services import llm_gate


def _dat_tran(monkeypatch, n: int) -> None:
    monkeypatch.setenv("ABES_AI_SONG_SONG", str(n))
    config.get_settings.cache_clear()


async def test_cong_chan_dung_tran(monkeypatch):
    """Dựng 10 việc nhưng trần 2 -> đỉnh đồng thời không bao giờ vượt 2."""
    _dat_tran(monkeypatch, 2)
    dang_bay = 0
    dinh = 0

    async def viec():
        nonlocal dang_bay, dinh
        async with llm_gate.cong():
            dang_bay += 1
            dinh = max(dinh, dang_bay)
            await asyncio.sleep(0.01)
            dang_bay -= 1

    await asyncio.gather(*(viec() for _ in range(10)))
    assert dinh == 2


async def test_cong_cho_phep_song_song_that(monkeypatch):
    """Trần rộng -> nhiều việc chạy chồng nhau (nếu không, gate đang tuần tự hoá oan)."""
    _dat_tran(monkeypatch, 8)
    dang_bay = 0
    dinh = 0

    async def viec():
        nonlocal dang_bay, dinh
        async with llm_gate.cong():
            dang_bay += 1
            dinh = max(dinh, dang_bay)
            await asyncio.sleep(0.01)
            dang_bay -= 1

    await asyncio.gather(*(viec() for _ in range(8)))
    assert dinh == 8


async def test_cong_dung_lai_trong_cung_mot_loop(monkeypatch):
    _dat_tran(monkeypatch, 3)
    assert llm_gate.cong() is llm_gate.cong()


def test_cong_khong_dinh_vao_loop_cu(monkeypatch):
    """Semaphore gắn vào loop ở lần dùng đầu; dùng lại qua loop khác sẽ nổ 'bound to a
    different event loop'. Mỗi loop phải có cổng riêng."""
    _dat_tran(monkeypatch, 2)

    async def lay():
        async with llm_gate.cong():
            return llm_gate.cong()

    a = asyncio.run(lay())
    b = asyncio.run(lay())
    assert a is not b
```

- [ ] **Step 2: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest tests/test_llm_gate.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'services.llm_gate'`

- [ ] **Step 3: Thêm `ai_song_song` vào config**

Trong `backend/config.py`, thêm ngay sau `ai_max_tokens_extract`:

```python
    # Trần số call LLM ĐANG BAY cùng lúc (mọi đường: chấm, ingest, decompose).
    # Mặc định thấp vì không biết sức chứa của vLLM/LiteLLM phía sau — xem mục "Vận hành" trong
    # spec để dò tăng dần. Phải <= 32: asyncio.to_thread dùng executor mặc định min(32, cpu+4).
    ai_song_song: int = 4
```

- [ ] **Step 4: Tạo `services/llm_gate.py`**

```python
"""Trần song song cho MỌI call LLM — một cổng CHUNG cho mọi đường gọi.

Vì sao một cổng chung chứ không phải mỗi tầng một cái: bước chấm lồng gather trong gather (tiêu
chí × nội dung) và ingest gather theo trang. Nếu mỗi tầng tự giới hạn thì TÍCH các trần mới là số
request thật dội xuống proxy — vượt xa sức chứa mà không ai chủ ý.

Semaphore tạo theo EVENT LOOP đang chạy, không phải một biến ở mức module: Python 3.11 gắn
Semaphore vào loop ở lần dùng đầu tiên, nên một biến dùng chung qua nhiều loop (pytest tạo loop
mới mỗi test) sẽ nổ "bound to a different event loop".
"""
from __future__ import annotations

import asyncio
from weakref import WeakKeyDictionary

from config import get_settings

_cong_theo_loop: "WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = (
    WeakKeyDictionary())


def cong() -> asyncio.Semaphore:
    """Semaphore của event loop đang chạy. Trần đọc từ `Settings.ai_song_song` lần đầu mỗi loop."""
    loop = asyncio.get_running_loop()
    sem = _cong_theo_loop.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(max(1, get_settings().ai_song_song))
        _cong_theo_loop[loop] = sem
    return sem
```

- [ ] **Step 5: Chạy test gate để xác nhận XANH**

Run: `cd backend && python -m pytest tests/test_llm_gate.py -q`
Expected: PASS (4 test).

- [ ] **Step 6: Viết test thất bại cho việc call LLM không còn chẹn loop**

Thêm vào cuối `backend/tests/test_ai_call.py`:

```python
async def test_ai_call_khong_chen_event_loop(monkeypatch):
    """Call LLM đồng bộ nằm trong async def sẽ chẹn loop -> mọi gather thành tuần tự.

    Đo bằng chính triệu chứng: hai call chạy chồng nhau thì tổng thời gian phải xấp xỉ MỘT call,
    không phải hai.
    """
    import asyncio
    import time

    import config
    from services import ai_client

    monkeypatch.setenv("ABES_AI_SONG_SONG", "4")
    config.get_settings.cache_clear()
    monkeypatch.setattr(ai_client.settings, "ai_mock", False)

    def cham(system, prompt, max_tokens=None):
        time.sleep(0.20)                      # ĐỒNG BỘ, đúng như litellm.completion
        return '{"ok": 1}'

    monkeypatch.setattr(ai_client, "_litellm_completion", cham)
    t0 = time.perf_counter()
    await asyncio.gather(ai_client.ai_call("s", "p", mock_key="k"),
                         ai_client.ai_call("s", "p2", mock_key="k"))
    trong = time.perf_counter() - t0
    assert trong < 0.35, f"hai call mất {trong:.2f}s — vẫn đang tuần tự"
```

- [ ] **Step 7: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest tests/test_ai_call.py -q -k khong_chen`
Expected: FAIL — `hai call mất 0.40s — vẫn đang tuần tự`

- [ ] **Step 8: Sửa `ai_call` gọi qua thread + gate**

Trong `backend/services/ai_client.py`, thêm import ở đầu file:

```python
import asyncio

from services.llm_gate import cong
```

Thêm hàm bọc ngay sau `_litellm_completion` (GIỮ NGUYÊN `_litellm_completion` là hàm đồng bộ cùng tên — test hiện có monkeypatch và gọi thẳng nó):

```python
async def _goi_llm(system: str, prompt: str, max_tokens: int | None = None) -> str:
    """Chạy lời gọi ĐỒNG BỘ của litellm trong thread để không chẹn event loop.

    Chỉ bọc đúng lời gọi HTTP: mọi thao tác DB/cache phải ở lại thread của event loop vì
    SQLAlchemy Session dùng chung không an toàn đa luồng.

    Giữ semaphore ở phạm vi MỘT LƯỢT gọi (hàm này), không bao cả vòng retry của `ai_call`: mỗi
    lượt có timeout=300s, ôm cổng qua hai lượt là một call hỏng giữ chỗ tới 600s và bỏ đói call khác.

    (`litellm.acompletion` là hướng sạch hơn khi nào muốn bỏ hẳn thread pool.)
    """
    async with cong():
        return await asyncio.to_thread(_litellm_completion, system, prompt, max_tokens)
```

Trong `ai_call`, thay dòng gọi đồng bộ:

```python
            raw = _litellm_completion(system, prompt, max_tokens=max_tokens)
```

bằng:

```python
            raw = await _goi_llm(system, prompt, max_tokens=max_tokens)
```

- [ ] **Step 9: Viết test thất bại cho `default_vision_fn`**

Thêm vào cuối `backend/tests/test_ai_determinism.py`:

```python
async def test_vision_khong_chen_event_loop(monkeypatch):
    """Đường vision cũng phải nhả loop — nó là đường tốn nhất (ingest từng trang)."""
    import asyncio
    import sys
    import time

    import config
    from experiment.evaluate import vision

    class _Cham:
        @staticmethod
        def completion(**kw):
            time.sleep(0.20)
            return {"choices": [{"message": {"content": '{"text": "x"}'}, "finish_reason": "stop"}]}

    monkeypatch.setitem(sys.modules, "litellm", _Cham)
    monkeypatch.setenv("ABES_AI_MOCK", "false")
    monkeypatch.setenv("ABES_AI_SONG_SONG", "4")
    config.get_settings.cache_clear()

    t0 = time.perf_counter()
    await asyncio.gather(vision.default_vision_fn("s", "p"), vision.default_vision_fn("s", "p2"))
    trong = time.perf_counter() - t0
    assert trong < 0.35, f"hai call vision mất {trong:.2f}s — vẫn đang tuần tự"
```

- [ ] **Step 10: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest tests/test_ai_determinism.py -q -k khong_chen`
Expected: FAIL — `hai call vision mất 0.40s — vẫn đang tuần tự`

- [ ] **Step 11: Sửa `default_vision_fn`**

Trong `backend/experiment/evaluate/vision.py`, tách thân đồng bộ ra hàm riêng rồi gọi qua thread. Thêm import `import asyncio` và `from services.llm_gate import cong` ở đầu file, rồi thay thân vòng lặp retry của `default_vision_fn`:

```python
def _completion_sync(system: str, prompt: str, images: list[bytes],
                     max_tokens: int | None, seed: int | None) -> Any:
    """Lời gọi litellm ĐỒNG BỘ. `import litellm` để TRONG hàm — test thay sys.modules['litellm']."""
    import litellm

    settings = get_settings()
    model = settings.ai_model
    if "/" not in model:
        model = f"openai/{model}"
    return litellm.completion(
        model=model, api_base=settings.ai_base_url,
        api_key=settings.ai_api_key or "sk-no-key",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": _content(prompt, list(images))},
        ],
        temperature=settings.ai_temperature,
        seed=settings.ai_seed if seed is None else seed,   # xem chú thích ai_seed (config)
        top_p=1.0,
        max_tokens=max_tokens or settings.ai_max_tokens,
        timeout=300,
    )
```

Và trong `default_vision_fn`, thay `resp = litellm.completion(...)` bằng:

```python
            async with cong():   # cổng ở phạm vi MỘT lượt, nhả trước khi retry
                resp = await asyncio.to_thread(_completion_sync, system, prompt, list(images),
                                               max_tokens, seed)
```

Bỏ phần dựng `model`/`import litellm` đã chuyển vào `_completion_sync`; giữ nguyên toàn bộ phần
parse JSON, `validate`, log `VISION:` và dựng `AiOutcome`.

- [ ] **Step 12: Chạy test để xác nhận XANH**

Run: `cd backend && python -m pytest tests/test_ai_call.py tests/test_ai_determinism.py tests/test_llm_gate.py -q`
Expected: PASS toàn bộ (gồm các test cũ monkeypatch `_litellm_completion` và `sys.modules["litellm"]`).

- [ ] **Step 13: Chạy full suite**

Run: `cd backend && python -m pytest -q` rồi `cd backend && python -m pytest experiment/evaluate/tests -q`
Expected: `185 passed` cộng số test mới, 0 failed; và `304 passed, 5 failed` (đúng 5 test đỏ baseline).

- [ ] **Step 14: Commit**

```bash
git add backend/services/llm_gate.py backend/config.py backend/services/ai_client.py \
        backend/experiment/evaluate/vision.py backend/tests/test_llm_gate.py \
        backend/tests/test_ai_call.py backend/tests/test_ai_determinism.py
git commit -m "perf(ai): call LLM chạy trong thread + cổng song song toàn cục, thôi chẹn event loop"
```

---

### Task 2: Ingest song song theo trang

**Files:**
- Create: `backend/experiment/evaluate/tests/dong_thoi.py`
- Modify: `backend/experiment/evaluate/ingest.py:126-163` (`_doc_file`)
- Test: `backend/experiment/evaluate/tests/test_ingest_song_song.py` (mới)

**Interfaces:**
- Consumes: `services.llm_gate.cong()` (Task 1) — không gọi trực tiếp, nó nằm dưới `vision_fn`.
- Produces: `experiment.evaluate.tests.dong_thoi.VisionDemDongThoi` — vision giả đếm số call đang bay và đỉnh; Task 3, 4, 5 dùng lại.

**Bối cảnh (đọc trước khi sửa):** đây là phần tốn nhất — đo trên log thật: ingest chiếm **731s trong 1507s** của một nhà thầu, 13 trang qua vision ở ~56s/trang. `_doc_file` hiện duyệt từng trang và `await` từng cái.

**Ràng buộc sống còn:** `fitz` (PyMuPDF) **không an toàn đa luồng**. Phải tách hai pha — render hết PNG trên thread của event loop TRƯỚC, rồi mới `gather` các lời gọi vision. Tuyệt đối không gọi `fitz` bên trong coroutine chạy song song.

- [ ] **Step 1: Tạo helper đo đồng thời**

Tạo `backend/experiment/evaluate/tests/dong_thoi.py`:

```python
"""Vision giả ĐẾM số call đang bay — dùng để chứng minh gather thật sự chạy chồng nhau.

Không có phép đo này thì một `gather` vẫn có thể tuần tự (vì bên dưới còn chỗ chẹn loop) mà test
kết quả vẫn xanh — đúng cái bệnh plan này chữa.
"""
from __future__ import annotations

import asyncio
from typing import Any

from services.ai_client import AiOutcome


class VisionDemDongThoi:
    """vision_fn giả: mỗi call nhường loop vài nhịp rồi trả `data`. Ghi lại đỉnh đồng thời."""

    def __init__(self, data: dict[str, Any] | None = None, nhip: int = 3):
        self._data = data if data is not None else {"text": "x"}
        self._nhip = nhip
        self.dang_bay = 0
        self.dinh = 0
        self.so_call = 0

    async def __call__(self, system: str, prompt: str, images: list[bytes] = (),
                       validate: Any = None, **kw: Any) -> AiOutcome:
        self.dang_bay += 1
        self.dinh = max(self.dinh, self.dang_bay)
        self.so_call += 1
        try:
            for _ in range(self._nhip):
                await asyncio.sleep(0)     # nhường loop: call khác có cơ hội vào
            data = dict(self._data)
            return AiOutcome("ok", validate(data) if validate else data, "fake")
        finally:
            self.dang_bay -= 1
```

- [ ] **Step 2: Viết test thất bại**

Tạo `backend/experiment/evaluate/tests/test_ingest_song_song.py`:

```python
"""Ingest đọc các trang SONG SONG — phần tốn nhất của một lượt chấm (731s/1507s đo trên log thật)."""
import fitz

from experiment.evaluate.ingest import ingest_hsdt
from experiment.evaluate.tests.dong_thoi import VisionDemDongThoi


def _pdf_scan(n: int) -> bytes:
    """PDF n trang KHÔNG có text nhúng -> mọi trang buộc đi đường vision."""
    d = fitz.open()
    for _ in range(n):
        d.new_page()
    return d.tobytes()


async def test_cac_trang_doc_song_song():
    vision = VisionDemDongThoi()
    pages = await ingest_hsdt([("scan.pdf", "bao_dam_du_thau", _pdf_scan(6))], vision, dpi=72)
    assert len(pages) == 6
    assert vision.so_call == 6
    assert vision.dinh > 1, "các trang vẫn đọc tuần tự"


async def test_thu_tu_trang_giu_nguyen():
    """gather giữ thứ tự — số trang phải đúng 1..n, không đảo."""
    vision = VisionDemDongThoi()
    pages = await ingest_hsdt([("scan.pdf", "bao_dam_du_thau", _pdf_scan(5))], vision, dpi=72)
    assert [p.trang for p in pages] == [1, 2, 3, 4, 5]


async def test_ket_qua_giong_het_duong_tuan_tu():
    """Bất biến quan trọng nhất: song song KHÔNG được đổi nội dung đọc ra."""
    pdf = _pdf_scan(4)
    a = await ingest_hsdt([("s.pdf", "bang_gia", pdf)], VisionDemDongThoi({"text": "A"}), dpi=72)
    b = await ingest_hsdt([("s.pdf", "bang_gia", pdf)], VisionDemDongThoi({"text": "A"}), dpi=72)
    assert [(p.trang, p.text, p.nguon_trich, p.canh_bao) for p in a] == \
           [(p.trang, p.text, p.nguon_trich, p.canh_bao) for p in b]


async def test_trang_co_text_nhung_van_khong_goi_vision():
    """Hồi quy: hai pha không được làm trang text nhúng lọt vào đường vision."""
    d = fitz.open()
    pg = d.new_page()
    pg.insert_text((72, 72), "Đây là trang có text nhúng đủ dài để không bị coi là scan")
    d.new_page()                                   # trang trắng -> vision
    vision = VisionDemDongThoi()
    pages = await ingest_hsdt([("hh.pdf", "don_du_thau", d.tobytes())], vision, dpi=72)
    assert vision.so_call == 1                     # CHỈ trang trắng đi vision
    assert pages[0].nguon_trich == "pdf_text" and pages[1].nguon_trich == "vision"


async def test_render_xong_het_truoc_khi_thuc_su_song_song(monkeypatch):
    """PyMuPDF KHÔNG an toàn đa luồng: mọi việc đụng fitz (kể cả render PNG) phải xong TRƯỚC khi
    pha 2 thả các call vision chạy chồng nhau. Test khoá đúng ranh giới đó bằng thứ tự sự kiện."""
    import experiment.evaluate.ingest as ing

    nhat_ky: list[str] = []
    goc = ing.page_to_png
    monkeypatch.setattr(ing, "page_to_png",
                        lambda page, dpi=200: (nhat_ky.append("render"), goc(page, dpi=dpi))[1])

    class _GhiNhan(VisionDemDongThoi):
        async def __call__(self, system, prompt, images=(), validate=None, **kw):
            nhat_ky.append("vision")
            return await super().__call__(system, prompt, images, validate, **kw)

    await ingest_hsdt([("scan.pdf", "bang_gia", _pdf_scan(4))], _GhiNhan(), dpi=72)
    assert nhat_ky == ["render"] * 4 + ["vision"] * 4, f"thứ tự sai: {nhat_ky}"
```

- [ ] **Step 3: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_ingest_song_song.py -q`
Expected: FAIL — `test_cac_trang_doc_song_song` báo `các trang vẫn đọc tuần tự` (đỉnh = 1). Ba test còn lại XANH sẵn (chúng khoá hành vi phải GIỮ).

- [ ] **Step 4: Sửa `_doc_file` thành hai pha**

Thay toàn bộ thân `_doc_file` trong `backend/experiment/evaluate/ingest.py` bằng:

```python
async def _doc_file(name: str, loai_ho_so: str, data: bytes, vision_fn: VisionFn,
                    dpi: int) -> tuple[list[PageRecord], bool]:
    """Đọc từng trang: có text nhúng -> TẤT ĐỊNH (0 call); còn lại -> vision đọc ảnh SONG SONG.

    HAI PHA, và ranh giới này là BẮT BUỘC: `fitz` (PyMuPDF) KHÔNG an toàn đa luồng, nên toàn bộ
    việc đụng tới `doc`/`page` (kể cả render PNG) phải xong hết ở pha 1 — chạy tuần tự trên thread
    của event loop — trước khi pha 2 thả các lời gọi vision chạy chồng nhau.

    Trả (records, du_de_cache); du_de_cache=False nếu có BẤT KỲ trang vision nào LỖI (cảnh báo
    không tính — cảnh báo vẫn được cache kèm theo).
    """
    # Pha 1 (đồng bộ, đụng fitz): quyết định đường đọc từng trang + render sẵn PNG cho trang vision.
    ket_qua: list[PageRecord | None] = []
    can_vision: list[tuple[int, bytes]] = []      # (chỉ số trong ket_qua, png)
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        for i, page in enumerate(doc, 1):
            tat_dinh = trich_trang_tat_dinh(page)
            if tat_dinh is not None:
                # Không render ảnh: trang này không cần vision, cũng không cần cờ thị giác.
                ket_qua.append(_record(name, loai_ho_so, i, {"text": tat_dinh}, b"",
                                       NGUON_PDF_TEXT))
                continue
            can_vision.append((len(ket_qua), page_to_png(page, dpi=dpi)))
            ket_qua.append(None)                  # giữ chỗ, điền ở pha 2
    finally:
        doc.close()

    # Pha 2 (song song, KHÔNG đụng fitz): gather giữ nguyên thứ tự nên khớp lại theo chỉ số.
    outs = await asyncio.gather(*(
        _doc_trang_vision(f"{name} tr{vi + 1}", png, vision_fn) for vi, png in can_vision))

    du_de_cache = True
    for (vi, png), (out, van_de) in zip(can_vision, outs):
        trang = vi + 1
        if out.status == "ok":
            if van_de:
                # KHÔNG im lặng: cảnh báo vào text để luật/eval hạ kết luận xuống 'cần làm rõ'.
                # Nhưng KHÔNG chặn cache: cache theo FILE, một trang cảnh báo mà chặn thì mọi
                # lần chấm sau phải OCR lại toàn bộ file.
                log.warning("[ingest] %s tr%d nghi bóc thiếu: %s", name, trang, "; ".join(van_de))
            ket_qua[vi] = _record(name, loai_ho_so, trang, out.data, png,
                                  canh_bao="; ".join(van_de))
        else:
            log.warning("[ingest] %s tr%d lỗi vision: %s", name, trang, out.error)
            du_de_cache = False
            ket_qua[vi] = _record(name, loai_ho_so, trang, {}, png)

    records = [r for r in ket_qua if r is not None]
    n_td = sum(1 for r in records if r.nguon_trich == NGUON_PDF_TEXT)
    log.info("[ingest] %s (%s): %d trang — %d đọc thẳng từ PDF, %d qua vision",
             name, loai_ho_so, len(records), n_td, len(records) - n_td)
    return records, du_de_cache
```

Thêm `import asyncio` vào đầu file nếu chưa có.

**Lưu ý về số trang:** ở pha 1, chỉ số trong `ket_qua` luôn bằng `số trang − 1` vì mỗi trang thêm đúng một phần tử (dù đi đường nào). Nên `vi + 1` chính là số trang — không được thay bằng biến đếm riêng.

- [ ] **Step 5: Chạy test để xác nhận XANH**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_ingest_song_song.py experiment/evaluate/tests/test_ingest.py experiment/evaluate/tests/test_ingest_cache.py experiment/evaluate/tests/test_ingest_tu_kiem.py -q`
Expected: PASS toàn bộ.

- [ ] **Step 6: Chạy full suite**

Run: `cd backend && python -m pytest experiment/evaluate/tests -q` rồi `cd backend && python -m pytest -q`
Expected: `304 passed + số test mới, 5 failed` (đúng 5 baseline); và `185 passed + test mới của Task 1, 0 failed`.

- [ ] **Step 7: Commit**

```bash
git add backend/experiment/evaluate/ingest.py \
        backend/experiment/evaluate/tests/dong_thoi.py \
        backend/experiment/evaluate/tests/test_ingest_song_song.py
git commit -m "perf(ingest): đọc các trang song song, render PNG xong hết trước khi gather"
```

---

### Task 3: Chấm song song các nội dung trong một tiêu chí

**Files:**
- Modify: `backend/experiment/evaluate/evaluate.py:266-286` (vòng `for i, nd in enumerate(nds)` trong `evaluate_criterion`)
- Test: `backend/experiment/evaluate/tests/test_evaluate_song_song.py` (mới)

**Interfaces:**
- Consumes: `experiment.evaluate.tests.dong_thoi.VisionDemDongThoi` (Task 2) — vision giả đếm đỉnh đồng thời.

**Bối cảnh (đọc trước khi sửa):** `evaluate_criterion` duyệt từng nội dung và `await` từng cái. Hai nhánh đồng bộ phải GIỮ NGUYÊN vị trí (chạy trước, không vào gather): `_gate_khong_ap_dung` (trả verdict N/A, 0 call) và `_phan_luat_cho_nd` (chọn luật cho từng nội dung). Chỉ phần `await` mới được gather.

**Bất biến sống còn:** thứ tự `verdicts` phải khớp thứ tự `nds`. Roll-up ngay dưới đó (`xet`, `kq`) không phụ thuộc thứ tự, nhưng bảng verdict hiện cho chuyên gia thì có — và test hồi quy hiện có bám vào thứ tự đó.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/experiment/evaluate/tests/test_evaluate_song_song.py`:

```python
"""Các nội dung trong một tiêu chí chấm SONG SONG — thứ tự verdict phải giữ nguyên."""
from experiment.evaluate.evaluate import evaluate_criterion
from experiment.evaluate.schema import KET_QUA_DAT, PageRecord
from experiment.evaluate.tests.dong_thoi import VisionDemDongThoi


def _page(loai: str, text: str = "nội dung") -> PageRecord:
    return PageRecord(file="f.pdf", trang=1, loai_ho_so=loai, text=text)


def _crit(n: int) -> dict:
    return {"nhom": "hop_le", "ten": "Tiêu chí", "hsdt_can_kiem_tra": ["don_du_thau"],
            "noi_dung_can_kiem_tra": [
                {"noi_dung_kiem_tra": f"nd{i}", "hsdt_kiem_tra": "don_du_thau",
                 "yeu_cau": "có", "thong_tin_bo_sung": ""} for i in range(n)]}


async def test_cac_noi_dung_cham_song_song():
    vision = VisionDemDongThoi({"ket_qua": "đạt", "bang_chung": "x"})
    ce = await evaluate_criterion(_crit(5), [_page("don_du_thau")], vision)
    assert vision.so_call == 5
    assert vision.dinh > 1, "các nội dung vẫn chấm tuần tự"
    assert ce.ket_qua == KET_QUA_DAT


async def test_thu_tu_verdict_giu_nguyen():
    """gather giữ thứ tự — verdict phải khớp đúng thứ tự nội dung trong tiêu chí."""
    vision = VisionDemDongThoi({"ket_qua": "đạt", "bang_chung": "x"})
    ce = await evaluate_criterion(_crit(6), [_page("don_du_thau")], vision)
    assert [v.noi_dung_kiem_tra for v in ce.verdicts] == [f"nd{i}" for i in range(6)]


async def test_gate_na_van_chay_truoc_va_khong_ton_call():
    """Nội dung bị gate 'không áp dụng' phải ra verdict N/A mà KHÔNG gọi vision — gate là nhánh
    đồng bộ, không được kéo vào gather."""
    from experiment.evaluate.schema import KET_QUA_KHONG_AP_DUNG, VendorProfile

    crit = _crit(2)
    crit["noi_dung_can_kiem_tra"][0]["ap_dung"] = "lien_danh"
    vision = VisionDemDongThoi({"ket_qua": "đạt", "bang_chung": "x"})
    ce = await evaluate_criterion(
        crit, [_page("don_du_thau")], vision,
        profile=VendorProfile(hinh_thuc="độc lập", nguon="khai báo", do_tin=1.0))
    assert ce.verdicts[0].ket_qua == KET_QUA_KHONG_AP_DUNG
    assert vision.so_call == 1                    # chỉ nội dung còn lại tốn call
```

- [ ] **Step 2: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_evaluate_song_song.py -q`
Expected: FAIL — `test_cac_noi_dung_cham_song_song` báo `các nội dung vẫn chấm tuần tự`. Hai test còn lại XANH sẵn.

- [ ] **Step 3: Sửa vòng lặp thành hai pha**

Trong `evaluate_criterion`, thay vòng `for i, nd in enumerate(nds):` (từ dòng `for i, nd in enumerate(nds):` tới hết `anh_em=anh_em or None))`) bằng:

```python
    # Pha 1 (đồng bộ): gate N/A và chọn luật — không tốn call, phải quyết TRƯỚC khi thả song song.
    # Verdict N/A giữ chỗ sẵn theo đúng chỉ số để thứ tự cuối cùng khớp thứ tự nội dung.
    cho: list[Verdict | None] = []
    viec: list[tuple[int, Any]] = []          # (chỉ số, coroutine)
    for i, nd in enumerate(nds):
        gated = _gate_khong_ap_dung(nd, profile, crit)   # N/A trước luật: khỏi tốn call
        if gated is not None:
            cho.append(gated)
            continue
        cho.append(None)
        skill = luat_cho_nd.get(i)
        if skill is not None:
            viec.append((i, run_skill(skill, by_type_, vendor_ctx, crit, vision_fn, nd=nd)))
            continue
        extra = crit.get("hsdt_can_kiem_tra", [])   # eval tự lọc ra tài liệu ngoài hồ sơ chính
        anh_em = [t for j, t in enumerate(ten_nds) if j != i and t]   # 1 gốc -> N need: phân công rõ
        viec.append((i, eval_noi_dung(nd, pages, vision_fn, extra_types=extra,
                                      vendor_ctx=vendor_ctx, profile=profile,
                                      yeu_cau_goc=str(crit.get("yeu_cau_goc", "")),
                                      anh_em=anh_em or None)))

    # Pha 2 (song song): gather giữ nguyên thứ tự nên khớp lại theo chỉ số đã ghi.
    for (i, _), v in zip(viec, await asyncio.gather(*(c for _, c in viec))):
        cho[i] = v
    verdicts: list[Verdict] = [v for v in cho if v is not None]
```

Xoá dòng `verdicts: list[Verdict] = []` khai báo cũ ở đầu hàm (nay dựng ở cuối pha 2). Thêm `import asyncio` vào đầu file nếu chưa có.

- [ ] **Step 4: Chạy test để xác nhận XANH**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_evaluate_song_song.py experiment/evaluate/tests/test_evaluate.py -q`
Expected: PASS toàn bộ (toàn bộ test hồi quy của `test_evaluate.py` phải xanh không sửa dòng nào).

- [ ] **Step 5: Chạy full suite**

Run: `cd backend && python -m pytest experiment/evaluate/tests -q` rồi `cd backend && python -m pytest -q`
Expected: chỉ 5 test đỏ baseline; suite `tests/` 0 đỏ.

- [ ] **Step 6: Commit**

```bash
git add backend/experiment/evaluate/evaluate.py \
        backend/experiment/evaluate/tests/test_evaluate_song_song.py
git commit -m "perf(eval): chấm song song các nội dung trong một tiêu chí, giữ nguyên thứ tự verdict"
```

---

### Task 4: Chấm song song các tiêu chí + các luật thường trực

**Files:**
- Modify: `backend/experiment/evaluate/pipeline.py:79-82` (vòng `for c in criteria`), `backend/experiment/evaluate/rules/registry.py:109-114` (`dispatch_standing`)
- Test: `backend/experiment/evaluate/tests/test_pipeline_song_song.py` (mới)

**Interfaces:**
- Consumes: `experiment.evaluate.tests.dong_thoi.VisionDemDongThoi` (Task 2).

**Bối cảnh (đọc trước khi sửa):** `evaluate_hsdt` duyệt từng tiêu chí và `await` từng cái; `dispatch_standing` là list-comprehension có `await` nên cũng tuần tự. `by_type` và `pages` chỉ được ĐỌC trong hai đường này nên chia sẻ giữa các coroutine là an toàn.

Sau Task 3, `evaluate_criterion` tự nó đã gather bên trong — task này lồng thêm một tầng gather bên ngoài. Đó là chủ ý: semaphore toàn cục ở Task 1 giữ tổng số request đang bay trong tầm kiểm soát, nên lồng gather KHÔNG dội quá tải.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/experiment/evaluate/tests/test_pipeline_song_song.py`:

```python
"""Tiêu chí và luật thường trực chạy SONG SONG trong một lượt chấm nhà thầu."""
from experiment.evaluate.rules.registry import (
    PHAM_VI_GOI, RuleRegistry, RuleSkill, dispatch_standing,
)
from experiment.evaluate.schema import PageRecord, Verdict
from experiment.evaluate.tests.dong_thoi import VisionDemDongThoi


def _page(loai: str) -> PageRecord:
    return PageRecord(file="f.pdf", trang=1, loai_ho_so=loai, text="nội dung")


def _skill(i: int) -> RuleSkill:
    async def handler(by_type, ctx, crit, vision_fn, *, nd=None, pkg=None):
        await vision_fn("sys", f"[RULE:{i}]")
        return Verdict(noi_dung_kiem_tra=f"luat{i}", hsdt_kiem_tra="don_du_thau", yeu_cau="",
                       thong_tin_bo_sung="", ket_qua="đạt", bang_chung="", trang=[], do_tin=0.0,
                       ghi_chu="", nguon_doc=[])
    return RuleSkill(id=f"luat{i}", ten=f"luat{i}", ho_so_can=["don_du_thau"],
                     can_vendor=False, handler=handler, pham_vi=PHAM_VI_GOI)


async def test_luat_thuong_truc_chay_song_song():
    reg = RuleRegistry()
    for i in range(4):
        reg.register(_skill(i))
    vision = VisionDemDongThoi()
    out = await dispatch_standing(reg, {"don_du_thau": [_page("don_du_thau")]}, None, vision)
    assert vision.dinh > 1, "các luật thường trực vẫn chạy tuần tự"
    assert [v.noi_dung_kiem_tra for v in out] == [f"luat{i}" for i in range(4)]   # giữ thứ tự


async def test_cac_tieu_chi_cham_song_song(monkeypatch):
    import experiment.evaluate.pipeline as pl

    crits = [{"nhom": "hop_le", "ten": f"TC{i}", "hsdt_can_kiem_tra": ["don_du_thau"],
              "noi_dung_can_kiem_tra": [{"noi_dung_kiem_tra": f"nd{i}",
                                         "hsdt_kiem_tra": "don_du_thau", "yeu_cau": "có",
                                         "thong_tin_bo_sung": ""}]} for i in range(5)]
    vision = VisionDemDongThoi({"ket_qua": "đạt", "bang_chung": "x"})

    async def fake_ingest(files, vision_fn, dpi=200, cache=None):
        return [_page("don_du_thau")]

    monkeypatch.setattr(pl, "ingest_hsdt", fake_ingest)
    r = await pl.evaluate_hsdt(crits, [], vision_fn=vision, registry=RuleRegistry())
    assert vision.dinh > 1, "các tiêu chí vẫn chấm tuần tự"
    assert [c.ten for c in r.criteria] == [f"TC{i}" for i in range(5)]            # giữ thứ tự
```

- [ ] **Step 2: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_pipeline_song_song.py -q`
Expected: FAIL cả hai — `các luật thường trực vẫn chạy tuần tự` và `các tiêu chí vẫn chấm tuần tự`.

- [ ] **Step 3: Sửa `dispatch_standing`**

Trong `backend/experiment/evaluate/rules/registry.py`, thêm `import asyncio` ở đầu file rồi thay thân `dispatch_standing`:

```python
async def dispatch_standing(registry: RuleRegistry, by_type: dict[str, list[PageRecord]],
                            vendor_ctx: VendorContext | None, vision_fn: Any,
                            *, pkg: PackageContext | None = None) -> list[Verdict]:
    """Kiểm tra thường trực — 1 lần/nhà thầu, verdict NGOÀI roll-up tiêu chí.

    Chạy song song: các luật độc lập nhau, chỉ ĐỌC `by_type`. `gather` giữ nguyên thứ tự nên thứ
    tự verdict trong báo cáo không đổi.
    """
    return list(await asyncio.gather(*(
        run_skill(s, by_type, vendor_ctx, {}, vision_fn, pkg=pkg) for s in registry.standing())))
```

- [ ] **Step 4: Sửa vòng lặp tiêu chí trong `evaluate_hsdt`**

Trong `backend/experiment/evaluate/pipeline.py`, thêm `import asyncio` ở đầu file rồi thay:

```python
    for c in criteria:
        result.criteria.append(await evaluate_criterion(
            c, pages, vision_fn, registry=registry, vendor_ctx=vendor, profile=profile,
            by_type=by_type))
```

bằng:

```python
    # Song song theo tiêu chí; `evaluate_criterion` tự gather bên trong theo nội dung. Lồng hai
    # tầng gather là chủ ý — cổng song song toàn cục (services/llm_gate) giữ tổng số request đang
    # bay trong tầm kiểm soát, nên không dội quá tải xuống proxy. `gather` giữ nguyên thứ tự.
    result.criteria.extend(await asyncio.gather(*(
        evaluate_criterion(c, pages, vision_fn, registry=registry, vendor_ctx=vendor,
                           profile=profile, by_type=by_type) for c in criteria)))
```

- [ ] **Step 5: Chạy test để xác nhận XANH**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_pipeline_song_song.py experiment/evaluate/tests/test_pipeline.py experiment/evaluate/tests/test_rules_registry.py -q`
Expected: PASS toàn bộ.

- [ ] **Step 6: Chạy full suite**

Run: `cd backend && python -m pytest experiment/evaluate/tests -q` rồi `cd backend && python -m pytest -q`
Expected: chỉ 5 test đỏ baseline; suite `tests/` 0 đỏ.

- [ ] **Step 7: Commit**

```bash
git add backend/experiment/evaluate/pipeline.py backend/experiment/evaluate/rules/registry.py \
        backend/experiment/evaluate/tests/test_pipeline_song_song.py
git commit -m "perf(eval): chấm song song các tiêu chí và các luật thường trực"
```

---

### Task 5: Đọc song song các chunk bảng giá

**Files:**
- Modify: `backend/experiment/evaluate/rules/lien_danh_phan_cong.py:310-321` (vòng `for i, chunk in enumerate(chunks, 1)`)
- Test: `backend/experiment/evaluate/tests/test_rules_lien_danh_song_song.py` (mới)

**Interfaces:**
- Consumes: `experiment.evaluate.tests.dong_thoi.VisionDemDongThoi` (Task 2).

**Bối cảnh (đọc trước khi sửa):** bảng giá thật đo được 15 trang ≈ 68.000 ký tự, chia thành nhiều chunk 6.000 ký tự — mỗi chunk một call, hiện chạy tuần tự.

**Đánh đổi đã được duyệt trong spec:** code hiện tại **dừng ở chunk lỗi ĐẦU TIÊN**; `gather` thì mọi chunk đều được gọi rồi mới xét lỗi. Verdict không đổi (vẫn báo lỗi kèm chỉ số chunk lỗi đầu tiên theo thứ tự), nhưng đường lỗi tốn thêm call. Chấp nhận vì đường lỗi hiếm còn đường thường nhanh hơn nhiều.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/experiment/evaluate/tests/test_rules_lien_danh_song_song.py`:

```python
"""Các chunk bảng giá đọc SONG SONG (bảng thật 15 trang ≈ 68.000 ký tự -> nhiều chunk)."""
from experiment.evaluate.rules.lien_danh_phan_cong import SKILL
from experiment.evaluate.schema import KET_QUA_LOI, PageRecord
from experiment.evaluate.tests.dong_thoi import VisionDemDongThoi
from services.ai_client import AiOutcome


def _p(trang: int, loai: str, text: str) -> PageRecord:
    return PageRecord(file="f.pdf", trang=trang, loai_ho_so=loai, text=text)


_TTLD = {"thanh_vien": [{"ten": "Công ty A", "mo_ta_cong_viec": "hạng mục 1",
                         "neu_ro_hang_muc": True, "ty_le_khai": 100.0}],
         "trang": [1], "ghi_chu": ""}


def _by_type(n_chunk: int) -> dict[str, list[PageRecord]]:
    """Mỗi trang bảng giá dài hơn ngân sách chunk -> mỗi trang thành một chunk riêng."""
    dai = "x" * 7000
    return {"thoa_thuan_lien_danh": [_p(1, "thoa_thuan_lien_danh", "bảng phân công")],
            "bang_gia": [_p(i, "bang_gia", dai) for i in range(1, n_chunk + 1)]}


class _Vision(VisionDemDongThoi):
    """Trả TTLD cho call giai đoạn 1, dữ liệu chunk cho các call sau."""

    async def __call__(self, system, prompt, images=(), validate=None, **kw):
        if "[RULE:lien_danh_ttld]" in prompt:
            self._data = dict(_TTLD)
        else:
            self._data = {"hang_muc": [{"stt": "1", "ten": "hm", "thanh_tien": 100.0,
                                        "thanh_vien": "Công ty A"}],
                          "dong_tong": [{"nhan": "TỔNG CỘNG", "gia_tri": 100.0}]}
        return await super().__call__(system, prompt, images, validate, **kw)


async def test_cac_chunk_doc_song_song():
    vision = _Vision()
    await SKILL.handler(_by_type(5), None, {}, vision)
    assert vision.dinh > 1, "các chunk bảng giá vẫn đọc tuần tự"


async def test_chunk_loi_van_bao_dung_chi_so_dau_tien():
    """Verdict không đổi: báo lỗi kèm chỉ số chunk lỗi ĐẦU TIÊN theo thứ tự, không phải chunk
    nào lỗi trước về đích."""
    class _Hong(_Vision):
        async def __call__(self, system, prompt, images=(), validate=None, **kw):
            if "[RULE:lien_danh_bang_gia]" in prompt and "x" * 100 in prompt:
                self.so_call += 1
                return AiOutcome("error", None, "fake", error="proxy hỏng")
            return await super().__call__(system, prompt, images, validate, **kw)

    v = await SKILL.handler(_by_type(3), None, {}, _Hong())
    assert v.ket_qua == KET_QUA_LOI
    assert "phần 1/3" in v.bang_chung
```

- [ ] **Step 2: Chạy test để xác nhận ĐỎ**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_rules_lien_danh_song_song.py -q`
Expected: FAIL — `test_cac_chunk_doc_song_song` báo `các chunk bảng giá vẫn đọc tuần tự`.

- [ ] **Step 3: Sửa vòng lặp chunk**

Trong `backend/experiment/evaluate/rules/lien_danh_phan_cong.py`, thêm `import asyncio` ở đầu file rồi thay:

```python
    ket_qua_chunks: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks, 1):
        o = await vision_fn(SYS_RULE_BANG_GIA, bang_gia_prompt(chunk, thanh_vien),
                            validate=validate_bang_gia_chunk, max_tokens=_MAX_TOKENS)
        if o.status == "error":
            # Thiếu 1 phần là tổng sai -> mọi tỷ lệ sai theo. KHÔNG kết luận trên dữ liệu thiếu.
            return _verdict(KET_QUA_LOI, trang=trang,
                            bang_chung=f"AI lỗi khi đọc bảng giá (phần {i}/{len(chunks)}): {o.error}",
                            ghi_chu="cần soi lại")
        ket_qua_chunks.append(o.data)
```

bằng:

```python
    # Song song theo chunk. Đánh đổi có chủ ý: bản cũ dừng ở chunk lỗi ĐẦU TIÊN, bản này gọi hết
    # rồi mới xét lỗi — đường lỗi tốn thêm call, đổi lại đường thường nhanh hơn nhiều. Verdict
    # KHÔNG đổi: vẫn báo chỉ số chunk lỗi đầu tiên THEO THỨ TỰ (gather giữ thứ tự), không phải
    # chunk nào lỗi trước về đích.
    outs = await asyncio.gather(*(
        vision_fn(SYS_RULE_BANG_GIA, bang_gia_prompt(chunk, thanh_vien),
                  validate=validate_bang_gia_chunk, max_tokens=_MAX_TOKENS)
        for chunk in chunks))
    for i, o in enumerate(outs, 1):
        if o.status == "error":
            # Thiếu 1 phần là tổng sai -> mọi tỷ lệ sai theo. KHÔNG kết luận trên dữ liệu thiếu.
            return _verdict(KET_QUA_LOI, trang=trang,
                            bang_chung=f"AI lỗi khi đọc bảng giá (phần {i}/{len(chunks)}): {o.error}",
                            ghi_chu="cần soi lại")
    ket_qua_chunks: list[dict[str, Any]] = [o.data for o in outs]
```

- [ ] **Step 4: Chạy test để xác nhận XANH**

Run: `cd backend && python -m pytest experiment/evaluate/tests/test_rules_lien_danh_song_song.py experiment/evaluate/tests/test_rules_lien_danh.py experiment/evaluate/tests/test_rules_lien_danh_chunk.py -q`
Expected: PASS trừ test đỏ baseline `test_rules_lien_danh.py::test_prompt_ttld_van_cap_con_bang_gia_thi_khong` (1 trong 5 test đỏ có sẵn).

- [ ] **Step 5: Chạy full suite**

Run: `cd backend && python -m pytest experiment/evaluate/tests -q` rồi `cd backend && python -m pytest -q`
Expected: chỉ 5 test đỏ baseline; suite `tests/` 0 đỏ.

- [ ] **Step 6: Commit**

```bash
git add backend/experiment/evaluate/rules/lien_danh_phan_cong.py \
        backend/experiment/evaluate/tests/test_rules_lien_danh_song_song.py
git commit -m "perf(rule): đọc song song các chunk bảng giá liên danh"
```

---

## Nghiệm thu cuối (sau khi xong cả 5 task)

- [ ] `cd backend && python -m pytest -q` — `185 passed` cộng test mới, **0 failed**.
- [ ] `cd backend && python -m pytest experiment/evaluate/tests -q` — `304 passed` cộng test mới, đúng **5 failed** baseline.
- [ ] `git log --oneline` có đủ 5 commit, mỗi commit một task.
- [ ] **Đo thật trên proxy** (cần AI thật, không chạy được offline): chấm lại một nhà thầu ở gói 62 sau khi `DELETE /api/v1/packages/1/cache`, so wall-clock với **1507s** ghi trong spec. Lặp với `ABES_AI_SONG_SONG` = 1, 2, 4, 8, 16 theo mục "Vận hành" của spec; dừng tăng khi thời gian không giảm thêm hoặc log bắt đầu có timeout/429.
- [ ] Ghi trần an toàn tìm được vào `backend/.env` và cập nhật lại mục "Vận hành" trong spec bằng số đo thật.
