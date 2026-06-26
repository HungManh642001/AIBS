# Thiết kế phần AI: Ánh xạ Tiêu chí → Loại hồ sơ → Đánh giá định tuyến

**Ngày:** 2026-06-26
**Phạm vi:** Thiết kế lại lớp AI của ABES để mỗi tiêu chí HSMT được đánh giá đúng trên loại hồ sơ HSDT tương ứng, thay vì gom toàn bộ HSDT thành một khối. Thiết kế pattern **chung cho cả 4 nhóm**, **kiểm chứng/triển khai trước trên nhóm Hợp lệ**.

---

## 1. Bối cảnh & Vấn đề

### Hiện trạng (yếu điểm)
Phần AI hiện tại (`services/extraction.py`, `services/evaluation/*.py`) hoạt động như sau:
- `extract_criteria(hsmt_pages)` → danh sách tiêu chí `{nhom, ten, yeu_cau, kieu, trong_so}`.
- Mỗi module đánh giá (legality/capacity/technical) **nối toàn bộ trang HSDT** thành một khối text rồi đưa cho `eval_one` chấm từng tiêu chí.

Hệ quả: AI **không biết** tiêu chí "Đơn dự thầu hợp lệ" thì phải soi *đơn dự thầu*, tiêu chí "Bảo đảm dự thầu" thì phải soi *thư bảo lãnh*. Không có lớp ánh xạ giữa *quy định trong HSMT* và *loại hồ sơ trong HSDT*. Dẫn chứng kém tin cậy, dễ nhiễu, không truy xuất nguồn gốc chuẩn.

### Mục tiêu
Xây dựng lớp ánh xạ rõ ràng: **tiêu chí → loại hồ sơ cần kiểm tra → nội dung đúng chỗ → đánh giá có dẫn chứng**, sao cho:
1. AI bóc tách quy định HSMT thành các điểm kiểm con có cấu trúc, gắn với đúng loại hồ sơ.
2. Đánh giá chỉ nhìn nội dung file đúng loại → dẫn chứng + số trang chính xác.
3. Chuyên gia kiểm soát được "đề cương chấm" trước khi chạy (PRD R-02, R-05).

### Quyết định nền (đã chốt khi brainstorming)
1. Thiết kế **pattern chung**, kiểm chứng trước trên **Hợp lệ**.
2. Catalog loại hồ sơ **hybrid**: bộ chuẩn theo Luật/NĐ + AI đề xuất loại mới khi gặp yêu cầu lạ.
3. HSDT **upload từng file riêng theo loại**; người dùng chọn loại lúc upload + **AI kiểm tra khớp** (cảnh báo nhầm).
4. Bóc tách thành **checklist con (sub-check) có cấu trúc**.
5. **Đề cương chấm chuyên gia review/sửa được** trước khi đánh giá.

### Phương án đã cân nhắc và loại bỏ
- **RAG / segmentation (Qdrant, PRD §6–7):** loại bỏ cho bài toán này. Vì HSDT đã tách file theo loại, định tuyến bằng metadata (`artifact_type`) vừa chính xác vừa nhẹ hơn hẳn. RAG chỉ cần khi một file chứa nhiều loại hoặc tài liệu quá lớn — để dành nâng cấp tương lai, không nằm trong phạm vi này.

---

## 2. Kiến trúc tổng thể — Pipeline 4 tầng

```
            HSMT (PDF)                         HSDT (nhiều file theo loại)
                │                                        │
                ▼                                        ▼
   ┌─────────────────────────┐              ┌──────────────────────────┐
   │ 1. BÓC TÁCH ĐỀ CƯƠNG     │              │ 3. GẮN NHÃN ARTIFACT      │
   │ AI: tiêu chí →           │              │ User chọn loại + AI kiểm  │
   │   required_artifacts +   │              │ tra khớp (cảnh báo nhầm)  │
   │   sub_checks[] + ngưỡng  │              │ → mỗi file có artifact_type│
   └───────────┬─────────────┘              └────────────┬─────────────┘
               │  (Catalog hybrid: chuẩn + AI mở rộng)    │
               ▼                                          │
   ┌─────────────────────────┐                            │
   │ 2. CHUYÊN GIA REVIEW     │                            │
   │ Sửa/thêm/xóa đề cương,   │                            │
   │ chỉnh ngưỡng, map lại    │                            │
   │ loại hồ sơ → CHỐT        │                            │
   └───────────┬─────────────┘                            │
               │                                          │
               └──────────────┬───────────────────────────┘
                              ▼
              ┌──────────────────────────────────────┐
              │ 4. ĐÁNH GIÁ ĐỊNH TUYẾN                 │
              │ Với mỗi tiêu chí:                      │
              │  • lấy đúng file(s) khớp required_     │
              │    artifacts (KHÔNG nối cả HSDT)       │
              │  • AI/Python chấm từng sub_check →     │
              │    evidence + page_ref trong đúng file │
              │  • thiếu file loại đó → FAIL "thiếu HS"│
              │  • tổng hợp sub_checks → verdict tiêu chí│
              └──────────────────────────────────────┘
```

**Khóa ghép trung tâm:** `artifact_type` (mã loại hồ sơ) nối hai phía — HSMT sinh ra *cần loại nào*, HSDT *khai báo file thuộc loại nào*. Định tuyến tiêu chí → nội dung trở thành tra cứu metadata.

**Ví dụ Hợp lệ:**
- "Đơn dự thầu hợp lệ" → `required_artifacts: [don_du_thau]`, sub_checks: `[đúng mẫu, có chữ ký/đóng dấu, người ký đủ thẩm quyền, còn hiệu lực]`.
- "Bảo đảm dự thầu" → `required_artifacts: [bao_dam_du_thau]`, sub_checks: `[có mặt, đúng hình thức, giá trị ≥ ngưỡng HSMT, thời hạn hiệu lực ≥ yêu cầu]`.

---

## 3. Artifact Catalog & Mô hình dữ liệu

### 3.1 Artifact Catalog (hybrid)
Module `services/artifact_catalog.py` định nghĩa danh mục chuẩn theo Luật 22/2023 & NĐ 24/2024. Mỗi mục: `{code, label, nhom_mac_dinh, mo_ta, aliases}` — `aliases` (danh sách từ khóa) dùng cho `validate_artifact`.

**Bộ chuẩn cho Hợp lệ (trọng tâm triển khai):**

| code | label | sub-checks điển hình |
|---|---|---|
| `don_du_thau` | Đơn dự thầu | đúng mẫu, chữ ký/đóng dấu, thẩm quyền, hiệu lực |
| `bao_dam_du_thau` | Bảo đảm dự thầu (thư BL/đặt cọc) | có mặt, đúng hình thức, giá trị ≥ ngưỡng, thời hạn ≥ yêu cầu |
| `thoa_thuan_lien_danh` | Thỏa thuận liên danh | có mặt (nếu liên danh), phân chia công việc |
| `tu_cach_phap_ly` | Tài liệu tư cách hợp lệ (ĐKKD…) | có mặt, còn hiệu lực |

**Khai báo sẵn cho các nhóm khác** (chưa làm sub-check đầy đủ, để pattern dùng lại): `bao_cao_tai_chinh`, `hop_dong_tuong_tu`, `ke_khai_nhan_su`, `ke_khai_thiet_bi`, `de_xuat_ky_thuat`, `catalogue_thong_so`, `bang_gia`.

**Cơ chế hybrid:** `extract_de_cuong` ánh xạ `required_artifacts` về `code` trong catalog. Nếu HSMT yêu cầu loại ngoài danh mục, AI trả `proposed_artifacts: [{code, label, ly_do}]`. Chuyên gia duyệt ở bước review đề cương → loại mới được thêm vào catalog **phạm vi gói thầu** (lưu trong dữ liệu gói, không sửa file catalog gốc).

### 3.2 Thay đổi mô hình dữ liệu

**Sửa entity hiện có:**
- `TenderDocument`: thêm
  - `artifact_type: str | None` — mã catalog (null cho HSMT).
  - `artifact_validation: dict` (JSON) — `{declared, ai_suggested, match: bool, confidence: float, note}`.
- `EvaluationCriteria`: thêm
  - `required_artifacts: list[str]` (JSON) — danh sách mã catalog.

**Bảng mới:**
- `evaluation_sub_check` — điểm kiểm con thuộc tiêu chí:
  - `id, criteria_id (FK), ten, check_type, thong_so (JSON), required_artifact (str), thu_tu (int), blocking (bool)`.
- `sub_check_result` — kết quả sub-check theo nhà thầu:
  - `id, sub_check_id (FK), vendor_id (FK), ket_qua (PASS|FAIL|PARTIAL), evidence (text), page_ref (JSON list), nguon_file (str: tên/loại file), ai_model (str), overridden (bool), ghi_chu (text)`.

**`EvaluationResult`** (giữ, là tổng hợp mức tiêu chí): `ket_qua, diem_so, dan_chung, so_trang, ghi_chu, overridden` — nay được **roll-up** từ `sub_check_result`. Vẫn cho phép override mức tiêu chí; thêm override mức sub-check qua `sub_check_result.overridden`.

**`check_type` taxonomy:** `{presence, form_match, signature_stamp, authority, value_threshold, date_validity, quantity_match, semantic_match}`.

**`thong_so` (JSON) ví dụ:** `{"nguong": "3% giá gói thầu", "gia_tri_so": 150000000, "don_vi": "VND", "so_ngay": 120}` — AI trích ở bước đề cương; chuyên gia sửa được.

**Migration:** SQLite demo — `init_db()` tạo bảng mới; dữ liệu demo có thể reset, không cần migration phức tạp.

---

## 4. Pipeline AI & Prompt

Ba hàm AI, đều qua `ai_client.ai_json` (LiteLLM + mock fallback), JSON-schema + few-shot để chạy thật với Qwen3.

### 4.1 `extract_de_cuong(hsmt_pages) -> list[criterion]`
Thay cho `extract_criteria`. Mỗi tiêu chí:
```json
{ "nhom": "hop_le", "ten": "Bảo đảm dự thầu",
  "required_artifacts": ["bao_dam_du_thau"],
  "kieu": "pass_fail", "trong_so": 0,
  "sub_checks": [
    {"ten": "Có bảo đảm dự thầu", "check_type": "presence", "thong_so": {}, "required_artifact": "bao_dam_du_thau", "blocking": true},
    {"ten": "Giá trị ≥ ngưỡng HSMT", "check_type": "value_threshold",
     "thong_so": {"nguong": "3% giá gói thầu", "gia_tri_so": 150000000, "don_vi": "VND"}, "required_artifact": "bao_dam_du_thau", "blocking": true},
    {"ten": "Thời hạn hiệu lực ≥ yêu cầu", "check_type": "date_validity",
     "thong_so": {"so_ngay": 120}, "required_artifact": "bao_dam_du_thau", "blocking": true}
  ],
  "proposed_artifacts": [] }
```

### 4.2 `validate_artifact(file_pages, declared_type) -> dict`
Chạy lúc upload. AI đọc nội dung file + `aliases` của `declared_type` trong catalog → `{match: bool, suggested_type: str, confidence: float, note: str}`. Nếu `match=False` → cảnh báo cho chuyên gia.

### 4.3 `evaluate_criterion(criterion, artifact_content_map) -> dict`
`artifact_content_map`: `{artifact_type: [pages...]}` — **chỉ chứa file khớp** `required_artifacts`. Prompt theo chuẩn PRD §7.3:
```
SYSTEM: Chuyên gia đánh giá HSDT theo Luật Đấu thầu VN. Chỉ trả JSON.
CONTEXT: <nội dung file 'bao_dam_du_thau', kèm số trang>
TASK: Chấm từng điểm kiểm sau cho hồ sơ này:
  1. Có bảo đảm dự thầu (presence)
  2. Giá trị ≥ 150.000.000 VND (value_threshold)
  3. Thời hạn hiệu lực ≥ 120 ngày (date_validity)
OUTPUT: {"sub_results":[{"sub_check_ten","result":"PASS|FAIL|PARTIAL","evidence","page_ref":[...]}]}
```

### 4.4 Tách tất định / AI
- `value_threshold`, `date_validity`: khi trích được số/ngày → **tính bằng Python** (`services/evaluation/checks.py`) như module Tài chính (`recalc_price_table` với `Decimal`). Có thể dùng AI chỉ để trích con số, còn so sánh do Python quyết định → kết quả chắc chắn.
- `presence, form_match, signature_stamp, authority, quantity_match, semantic_match`: **AI chấm ngữ nghĩa**, bắt buộc kèm `evidence` + `page_ref`.

### 4.5 Tổng hợp (Python, không phải AI)
verdict tiêu chí: `FAIL` nếu có sub-check `blocking` nào FAIL; `PASS` nếu tất cả PASS; còn lại `PARTIAL`. Điểm = tỉ lệ sub-check đạt (cho `kieu=score`).

---

## 5. Luồng đánh giá định tuyến & Ngoại lệ

### 5.1 Luồng chính (mỗi nhà thầu × mỗi tiêu chí)
```
cho tiêu chí C:
  required ← C.required_artifacts
  files    ← TenderDocument của vendor có artifact_type ∈ required
  cho mỗi sub_check s của C:
      arts ← files khớp s.required_artifact
      nếu arts rỗng:                                   # THIẾU HỒ SƠ
          s.result = FAIL, evidence = "Thiếu hồ sơ: <label>"   # không gọi AI
      elif s.check_type ∈ {value_threshold, date_validity} và có số/ngày:
          s.result = tính tất định bằng Python
      else:
          s.result = AI chấm trên nội dung arts (+ evidence, page_ref)
  verdict(C) = tổng hợp sub_results
```
AI chỉ nhìn nội dung file đúng loại → dẫn chứng + số trang nằm trong đúng hồ sơ (PRD §7.4).

### 5.2 Bảng xử lý ngoại lệ

| Tình huống | Xử lý |
|---|---|
| **Thiếu file loại yêu cầu** | Sub-check `blocking` → `FAIL` "Thiếu hồ sơ: \<label\>", không gọi AI; tiêu chí FAIL |
| **Đầy đủ thành phần** (tiêu chí completeness) | Tính bằng Python: tập artifact yêu cầu của gói = hợp các `required_artifacts` trong đề cương → đối chiếu file đã nộp → `% đầy đủ + danh sách thiếu` |
| **File nhầm loại** | `validate_artifact` trả `match=False` → cảnh báo; chuyên gia gắn lại nhãn / tải lại; đánh giá dùng nhãn đã chốt |
| **Nhiều file cùng loại** | Nối nội dung các file cùng `artifact_type`; `page_ref` kèm nhãn file (`nguon_file`) để truy ngược |
| **Tiêu chí cần nhiều loại** | Mỗi sub_check tự mang `required_artifact` riêng → định tuyến đúng tập file con |
| **AI lỗi / timeout** | try/except theo tiêu chí → đánh dấu "lỗi", pipeline chạy tiếp (NFR §5.3) |
| **Thiếu ngưỡng số/ngày** | `thong_so` trích ở bước đề cương; trống → chuyên gia điền khi review, hoặc AI ước lượng kèm cảnh báo |

### 5.3 Quan hệ với code hiện có
Module Tài chính (`recalc_price_table`, `Decimal`) là một dạng "đánh giá tất định trên artifact `bang_gia`". Pattern mới **tổng quát hóa** tinh thần đó cho `value_threshold`/`date_validity` của nhóm Hợp lệ.

---

## 6. Chiến lược Mock/Thật, Phạm vi code & Kiểm thử

### 6.1 Mock/thật
Giữ `ai_client` (LiteLLM + mock fallback). Bổ sung mock có cấu trúc mới cho `extract_de_cuong`, `validate_artifact`, `evaluate_criterion` → demo chạy không cần GPU. Bật `ABES_AI_MOCK=0` chạy thật Qwen3.

### 6.2 Phạm vi code (kiểm chứng trên Hợp lệ)

**Mới:**
- `services/artifact_catalog.py` — danh mục + tra cứu + mở rộng hybrid (phạm vi gói)
- `services/artifact_classify.py` — `validate_artifact`
- `services/evaluation/checks.py` — helper tất định `presence`, `value_threshold`, `date_validity`
- Bảng `evaluation_sub_check`, `sub_check_result` (trong `models.py`)
- Endpoint đề cương: `GET /packages/{id}/de-cuong`, `PUT /packages/{id}/de-cuong`, `POST /packages/{id}/de-cuong/confirm`
- Frontend: màn **"Đề cương chấm"** (sửa tiêu chí→loại HS→sub-check + ngưỡng), select `artifact_type` lúc upload + cảnh báo nhầm, kết quả hiện breakdown theo sub-check + override mức sub-check

**Sửa:**
- `services/extraction.py` → `extract_de_cuong`
- `services/evaluation/base.py` → `evaluate_criterion` chạy sub-check + tổng hợp
- `services/evaluation/legality.py` → định tuyến theo artifact (proving ground)
- `models.py`: `TenderDocument` +`artifact_type`/`artifact_validation`; `EvaluationCriteria` +`required_artifacts`
- `routers/documents.py` (nhận `artifact_type` + chạy `validate_artifact`)
- `routers/evaluation.py` (định tuyến theo artifact + trả `sub_results`; bước đề cương tách khỏi bước evaluate)

### 6.3 Kiểm thử (mock-driven, TDD)
- Catalog: tra cứu + mở rộng hybrid
- `extract_de_cuong`: tiêu chí có `required_artifacts` + `sub_checks` đúng shape
- `validate_artifact`: khớp / nhầm loại
- **Định tuyến**: tiêu chí → đúng file artifact; **thiếu file → FAIL "thiếu hồ sơ" không gọi AI**
- Helper tất định: `value_threshold` (≥ ngưỡng), `date_validity` (đủ số ngày), `presence`
- Tổng hợp: sub_results → verdict tiêu chí (FAIL/PASS/PARTIAL) theo `blocking`
- Completeness: % đầy đủ + danh sách thiếu
- E2E Hợp lệ: upload 2 file (`don_du_thau`, `bao_dam_du_thau`) → đề cương → đánh giá → sub-check + dẫn chứng

### 6.4 Ngoài phạm vi (YAGNI)
RAG/Qdrant; bộ sub-check đầy đủ cho 3 nhóm còn lại (dùng lại pattern sau); auth.

---

## 7. Tiêu chí thành công
1. Tiêu chí Hợp lệ trong đề cương có `required_artifacts` + `sub_checks` đúng cấu trúc, chuyên gia sửa được trước khi chạy.
2. Đánh giá định tuyến: mỗi tiêu chí chỉ chấm trên file đúng loại; dẫn chứng + số trang nằm trong đúng hồ sơ.
3. Thiếu hồ sơ loại yêu cầu → tự động FAIL "thiếu hồ sơ" không gọi AI.
4. `value_threshold`/`date_validity` cho kết quả tất định khi số liệu trích được.
5. Demo chạy được với mock (không GPU); cấu trúc sẵn sàng cho Qwen3 thật.
6. Pattern tổng quát, 3 nhóm còn lại có thể áp dụng lại mà không đổi kiến trúc.
