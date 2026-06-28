# Khắc phục độ chính xác AI (P0 + P1) — Design Spec

**Ngày:** 2026-06-27
**Phạm vi:** P0 (nổi lỗi thay vì mock, locator dải mục) + P1 (chunking map-reduce 2 bước, Chain-of-Thought, validate schema).
**Tham chiếu phân tích:** lỗ hổng AI đã xác định trong phiên 2026-06-27 (chunking/locator, thiếu CoT, single-turn JSON, mock fallback im lặng).

---

## 1. Bối cảnh & mục tiêu

Pipeline AI hiện tại (`services/ai_client.py`, `extraction.py`, `hsmt_locator.py`, `evaluation/base.py`, `evaluation/checks.py`) có 4 lỗ hổng làm giảm độ chính xác:

1. **Chunking sơ khai + locator mong manh** — cắt cứng `text[:12000]`, locator lấy lẻ trang chứa keyword (mất trang nội dung), fallback nạp nhầm 12k đầu.
2. **Thiếu Chain-of-Thought** — mọi prompt "Trả JSON: {schema}"; `response_format=json_object` ép token đầu là `{`, cấm suy luận; field `result` đứng trước `evidence`.
3. **Single-turn JSON dễ lỗi/ảo giác** — `json.loads` lỗi bất kỳ → mock; không repair/retry/`max_tokens`; không validate schema/catalog/page_ref.
4. **Mock fallback im lặng** — mọi lỗi (mạng/parse/timeout) quy về mock trông như thật, persist như phán quyết thật.

**Mục tiêu spec này:** hệ thống **không bao giờ bịa âm thầm**; suy luận có CoT; trích xuất phân rã + chunk theo cấu trúc; mọi lỗi nổi rõ để chuyên gia xử lý.

**Nguyên tắc xuyên suốt:** phân biệt **mock chủ ý** (`ABES_AI_MOCK=1`, dev) với **lỗi runtime** (chế độ thật) — lỗi runtime không bao giờ trả dữ liệu giả.

---

## 2. Hợp đồng gọi AI mới (P0)

### 2.1 Kiểu trả về có trạng thái

Thay `ai_json(system, prompt, *, mock_key) -> dict` (nuốt lỗi) bằng:

```python
@dataclass
class AiOutcome:
    status: str            # "ok" | "error"
    data: dict | None      # JSON đã parse + validate; None khi error
    model: str             # "qwen3-27b" | "mock"
    error: str | None      # mô tả lỗi khi status="error"
```

```python
async def ai_call(system: str, prompt: str, *, mock_key: str,
                  validate: Callable[[dict], dict] | None = None) -> AiOutcome
```

### 2.2 Hành vi

- **`ABES_AI_MOCK=1`:** trả `AiOutcome(status="ok", data=MOCK[mock_key], model="mock")`. (Mock chủ ý — giữ để demo không cần GPU.)
- **Chế độ thật:**
  1. Gọi LiteLLM với `temperature=0` (tái lập) và `max_tokens` cấu hình (mặc định 4096, riêng extract bước-1 lớn hơn).
  2. **Bóc JSON** từ phản hồi qua `extract_json()` (xem §4): gỡ ```json fence, lấy object ngoài cùng.
  3. `json.loads` → nếu có `validate`, chạy validate (Pydantic). 
  4. Lỗi mạng/timeout/parse/validate → **1 retry** (gọi lại nguyên văn). Vẫn lỗi → `AiOutcome(status="error", data=None, error=...)`. **KHÔNG trả mock.**
- Bỏ `response_format={"type":"json_object"}` (xung đột với CoT — xem §5).
- Bỏ việc gắn `data["_model"]`; model nằm ở `AiOutcome.model`.

### 2.3 Tác động caller

- `eval_one`, `evaluate_criterion` (AI branch), `validate_artifact`, `extract_rubric` nhận `AiOutcome`.
- `status="error"` → caller tạo kết quả với `ket_qua="ERROR"`, `evidence=outcome.error`, không tính vào PASS/FAIL.
- **Vòng lặp tiêu chí/sub-check không dừng** khi 1 lượt lỗi — tiếp tục các mục còn lại.

### 2.4 Caller legacy

`extraction.py` còn `extract_criteria()` và `map_hsdt()` — di sản trước refactor rubric, **không còn caller production** (chỉ test của chính chúng tham chiếu; đã thay bằng `extract_rubric` + `_artifact_map`). Để khỏi giữ `ai_json` chỉ phục vụ code chết: **xoá hai hàm này + test của chúng + mock key `extract_criteria`/`map_hsdt`** trong cùng đợt. Sau đó `ai_json` bị loại hoàn toàn, mọi caller dùng `ai_call`.

---

## 3. Locator dải mục + chunking map-reduce (P0 + P1)

### 3.1 Locator viết lại (`hsmt_locator.py`) — P0

```python
def locate_hsmt_sections(pages: list[dict]) -> dict
# -> {"tcdg": {"located": bool, "pages": [...]},
#     "bds":  {"located": bool, "pages": [...]}}
```

- **Chuẩn hoá** mỗi trang: lowercase + bỏ dấu (`unicodedata` NFD) để chống lỗi OCR/biến thể.
- Từ điển heading mở rộng cho TCĐG ("tieu chuan danh gia", "chuong iii tieu chuan", "tieu chuan danh gia ho so du thau"...) và BDS ("bang du lieu dau thau", "bds", "bang du lieu").
- Tìm **trang bắt đầu** (trang chứa heading); lấy **dải** từ trang đó đến trang bắt đầu của heading mục lớn kế tiếp (hoặc hết tài liệu). Trả nguyên dải, không lẻ trang.
- **Không tìm thấy** → `located=false`, `pages=[]`. **Không** fallback nạp toàn bộ/12k đầu.

### 3.2 Xử lý khi không định vị được — P0 (KHÔNG làm UI)

- `rubric.extract` kiểm `tcdg.located`:
  - `false` → trả `fail("Không định vị được mục Tiêu chuẩn đánh giá trong HSMT — kiểm tra lại file HSMT", 422)`. Không gọi AI, không bịa.
- `bds.located=false` → vẫn trích tiêu chí nhưng mọi ngưỡng số/ngày đặt `can_review=true` (không có nguồn BDS để tra).
- *(UI chỉ định dải trang thủ công: out of scope, để plan sau.)*

### 3.3 Trích xuất 2 bước + chunking (`extraction.py`) — P1

Thay `extract_rubric(sections)` 1-shot bằng:

```python
# Trả về AiOutcome: status="ok" data={"criteria":[...]} | status="error" (bước 1 hỏng)
async def extract_rubric(sections) -> AiOutcome            # điều phối 2 bước
async def _list_criteria(tcdg_pages) -> AiOutcome          # bước 1 (data["criteria"])
async def _detail_criterion(crit, tcdg_chunk, bds_pages) -> AiOutcome  # bước 2
```

`extract_rubric` luôn trả `AiOutcome` (đồng nhất với §2). Router đọc `outcome.status`: `error` → trả lỗi 422; `ok` → lấy `outcome.data["criteria"]`.

- **Bước 1 — liệt kê:** prompt trả *danh sách* tiêu chí (`nhom`, `ten`, `required_artifacts`). Output nhẹ → ít cắt cụt. `status="error"` → đẩy lên router (toàn bộ trích xuất dừng).
- **Bước 2 — chi tiết:** mỗi tiêu chí 1 lượt gọi → `sub_checks` + `thong_so` (ngưỡng), tra chéo BDS, `can_review` nếu không giải được. Lỗi 1 tiêu chí → tiêu chí đó đánh dấu `error`, các tiêu chí khác vẫn trích.
- **Chunking theo cấu trúc:** `chunk_pages(pages, max_chars, overlap)` cắt theo ranh giới trang/điều (không cắt giữa dòng), có overlap. Khi dải TCĐG vượt ngân sách: chạy bước 1 trên từng chunk rồi **merge khử trùng theo `ten`** (chuẩn hoá bỏ dấu).
- Bỏ `_join(...)[:12000]` cắt cứng; thay bằng chunk có ranh giới.

---

## 4. Prompt CoT + bóc/validate JSON (P1 + P0)

### 4.1 Template CoT (`services/prompts.py` mới)

- Dùng chung cho extract & evaluate. Cấu trúc phản hồi yêu cầu:
  1. **Khối suy luận ngắn** (gạch đầu dòng: đọc yêu cầu → đối chiếu hồ sơ → kết luận).
  2. Một khối ```json {…}``` duy nhất ở cuối.
- Trong JSON: **`evidence`/`reasoning` đứng TRƯỚC `result`** (model sinh trái→phải nên lý lẽ dẫn dắt phán quyết).
- Kèm **định nghĩa thang**: PASS (đáp ứng đầy đủ) / FAIL (vi phạm điều kiện tiên quyết) / PARTIAL (đáp ứng một phần) + yêu cầu **trích đúng câu/điều khoản** vào `evidence`.

### 4.2 Bóc JSON (`services/json_utils.py` mới)

```python
def extract_json(raw: str) -> dict   # ném ValueError nếu không bóc được
```

- Ưu tiên nội dung trong ```json ... ```; nếu không có, lấy object `{...}` ngoài cùng bằng cân bằng ngoặc.
- Repair nhẹ: gỡ fence, bỏ dấu phẩy thừa trước `}`/`]`.

### 4.3 Validate schema (Pydantic) — P0

- Model cho từng loại output: `CriterionModel`, `SubCheckModel`, `EvalVerdictModel`, `SubVerdictModel`, `ValidateArtifactModel`.
- Sai khoá/thiếu trường bắt buộc → ném lỗi → `ai_call` coi là `error` (không persist rác).
- **`required_artifact` ngoài catalog** → KHÔNG auto-FAIL nhà thầu; đánh dấu sub-check `can_review` + ghi rõ "AI đề xuất loại hồ sơ ngoài danh mục".
- **`page_ref`**: lọc bỏ phần tử không phải int; clamp về `[1, số_trang_thật]`; ngoài khoảng → loại.

---

## 5. Hiển thị lỗi xuyên suốt (P0)

### 5.1 Backend

- `SubCheckResult.ket_qua` nhận thêm giá trị `"ERROR"` (chuỗi — **không đổi schema, không migration**). `evidence` chứa lý do lỗi.
- `aggregate_subresults`: nếu có sub `ERROR` → verdict tiêu chí = `"ERROR"` (không tính PASS/FAIL/PARTIAL). `evaluate` set trạng thái gói phản ánh còn lỗi.
- `results` trả `ket_qua="ERROR"` cho sub/criteria lỗi như bình thường.

### 5.2 Frontend

- `SubResult.ai_model` đã có; thêm xử lý `result="ERROR"`:
  - Chip nguồn AI thêm kiểu **`error`** (đỏ) + nhãn "AI lỗi — cần xử lý".
  - `ResultPill` thêm trạng thái `ERROR` (đỏ đậm, khác FAIL).
  - Verdict tiêu chí có sub ERROR → hiển thị "Cần review".
- **Chặn Xuất Word/Excel** khi còn ERROR: nút disabled + tooltip "Còn N điểm kiểm AI lỗi, hãy xử lý trước khi xuất".

---

## 6. Cấu hình (config.py)

Thêm:
- `ai_temperature: float = 0.0`
- `ai_max_tokens: int = 4096`
- `ai_max_tokens_extract: int = 8192`
- `ai_chunk_chars: int = 12000`
- `ai_chunk_overlap: int = 800`

---

## 7. Phạm vi

**TRONG phạm vi:** §2–§6 ở trên (P0 + P1).

**NGOÀI phạm vi (deferred — plan sau):**
- P2: sửa `_max_number`/`_days` trích số theo ngữ cảnh nhãn + đơn vị/tiền tệ (`checks.py`).
- P3: grounding-check (evidence là substring của trang nguồn), chống prompt-injection từ nội dung HSDT.
- UI chuyên gia chỉ định dải trang TCĐG/BDS khi locator trượt.
- Hệ thống migration (Alembic) — vẫn SQLite demo, các thay đổi spec này không cần migration.

---

## 8. Kiểm thử

**Unit:**
- `hsmt_locator`: dải mục liên tục; trang OCR sai dấu vẫn match (chuẩn hoá); `located=false` khi vắng heading (không fallback nạp toàn bộ); BDS thiếu → `can_review`.
- `json_utils.extract_json`: fence, object lồng, dấu phẩy thừa, rỗng → ValueError.
- `ai_call`: mock chủ ý trả ok; chế độ thật parse lỗi → retry → error (monkeypatch `_litellm_completion` raise/trả rác); validate fail → error.
- Pydantic validate: thiếu trường → reject; `required_artifact` ngoài catalog → can_review; `page_ref` ngoài khoảng → loại.
- `chunk_pages` + merge khử trùng theo `ten`.
- `aggregate_subresults`: có ERROR → verdict ERROR.

**E2E (Hợp lệ):**
- Luồng đủ: HSMT → locator dải mục → trích 2 bước (mock) → đánh giá → sub-check.
- Ép 1 lượt AI lỗi (chế độ thật giả lập) → kết quả ra `ERROR`, **không** có dữ liệu mock, **không** persist phán quyết giả; báo cáo bị chặn.

---

## 9. Rủi ro & lưu ý

- **Bỏ `json_object` mode** đánh đổi: model có thể trả JSON kém chuẩn hơn → bù bằng `extract_json` + retry + validate.
- **2 bước trích** tăng số lượt gọi (1 + N tiêu chí) → chậm/đắt hơn 1-shot; chấp nhận để đổi lấy độ chính xác (giảm cắt cụt/ảo giác). `temperature=0` giúp tái lập.
- **Giá trị `ERROR` trong `ket_qua`**: các chỗ đọc cũ giả định chỉ PASS/FAIL/PARTIAL cần được rà (báo cáo `reports.py`, tổng hợp) để không vỡ — đưa vào plan như một bước rà soát.
