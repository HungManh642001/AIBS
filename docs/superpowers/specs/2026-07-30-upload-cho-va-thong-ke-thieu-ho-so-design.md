# Thiết kế: bỏ chờ khi upload HSDT + thống kê thiếu hồ sơ ở trang Kết quả

> Spec thiết kế. Ngày: 2026-07-30. Nhánh: `feat/ai-accuracy-remediation`.
> Hai phần độc lập nhau — có thể triển khai / merge riêng.

## Context

Hai vấn đề người dùng báo sau khi dùng thử:

1. **Tải HSDT lên phải chờ một lúc.** Không có phản hồi nào trong lúc chờ, người dùng không biết
   hệ thống đang làm gì hay đã treo.
2. **Trang Kết quả đánh giá chưa thống kê thiếu hồ sơ.** Chuyên gia không thấy được nhà thầu nộp
   thiếu loại hồ sơ nào, cũng không thấy bao nhiêu tiêu chí không chấm được vì lý do đó.

---

## Phần A — Upload HSDT hết chờ

### Nguyên nhân gốc

`backend/routers/documents.py:74-82` (`upload_document`) chạy **đồng bộ** và block trên
`validate_artifact` — một call LLM (`services/artifact_classify.py:29` → `ai_call`, timeout 300s
mỗi lần, `ai_client` thử 2 lần).

Điểm mấu chốt: `services/documents.py::extract_document` **cố ý trả `[]` cho `pdf_scan`** — HSDT
scan không OCR ở bước upload nữa, để Qwen vision đọc ảnh ở bước chấm. Nên với HSDT bản scan:

```
extract_document(...) -> []  ->  _text([]) -> ""  ->  prompt gửi LLM có nội dung RỖNG
```

Nghĩa là **ca phổ biến nhất** (HSDT thực tế là bản scan) đang chờ một call LLM không thể cho kết
luận có nghĩa. Kết quả `match=false` từ nội dung rỗng còn sinh cảnh báo "Nghi tải nhầm loại" sai.

Cùng lỗi ở `documents.py:111-113` (`update_document_type`): file scan có `extracted_text = "[]"`
nên mỗi lần chuyên gia đổi loại hồ sơ lại tốn thêm một call LLM trên nội dung rỗng.

Nguyên nhân thứ hai, độc lập: `frontend/src/pages/PackageDetail.tsx:144` (`uploadDoc`) **không có
chỉ báo loading nào** — không spinner, không disable nút, chỉ `message.success` sau khi xong. Ngay
dưới nó, nút "Chạy đánh giá" (`:181`) thì có `message.loading({ duration: 0 })`.

### Thay đổi

**Backend.** Chỉ gọi `validate_artifact` khi thực sự có text để đọc:

- `upload_document`: điều kiện `if doc.artifact_type and pages:` thay cho `if doc.artifact_type:`.
- `update_document_type`: cùng cách — `pages` rỗng thì bỏ qua, không gọi LLM.

Khi bỏ qua, `artifact_validation` để `None`, **không dựng kết quả giả**. UI đã xử lý `None` sẵn:
`PackageDetail.tsx:152` chỉ cảnh báo khi `match === false`.

Hệ quả: upload HSDT scan trả về ngay sau khi lưu file + ghi DB (0 call LLM). File PDF có text
nhúng vẫn được kiểm loại như cũ.

**Frontend.** `uploadDoc` dùng đúng khuôn của nút "Chạy đánh giá": `message.loading` với `key` cố
định và `duration: 0` khi bắt đầu, thay bằng `message.success` / `message.error` cùng `key` khi
xong. Thêm state `uploading` để disable nút Upload trong lúc chờ, tránh bấm chồng sinh nhiều bản
ghi tài liệu.

### Giới hạn đã biết (không chữa ở đây)

Kiểm loại hồ sơ với **PDF có text nhúng** vẫn là call LLM đồng bộ trong request. Với file dài,
người dùng vẫn chờ — nhưng nay có phản hồi rõ, và đây không phải dạng file HSDT phổ biến. Chuyển
`validate_artifact` sang chạy nền là phương án đã cân nhắc và loại: nó thêm hạ tầng nền + trạng
thái trung gian trong UI, không đáng cho một demo nội bộ.

### Files chạm

`backend/routers/documents.py`, `frontend/src/pages/PackageDetail.tsx`,
`backend/tests/test_documents_api.py`.

---

## Phần B — Thống kê thiếu hồ sơ ở trang Kết quả

### Hiện trạng

Dữ liệu đã có sẵn nhưng không được dùng để trả lời câu hỏi này:

- `HsdtVendorEval.ho_so_nhan_duoc` (loại hồ sơ + tên file + số trang) được trả trong payload
  `results` (`routers/evaluation.py:270`), nhưng `Evaluation.tsx:33-37` chỉ dùng nó để **tra tên
  file** cho cột bằng chứng.
- Verdict cấp nội dung vẫn mang `ket_qua = "thiếu hồ sơ"`, nhưng ở roll-up
  (`_rollup`, `routers/evaluation.py:86`) nó bị cuộn vào `"cần làm rõ"` — nên **tiêu chí không bao
  giờ mang kết quả "thiếu hồ sơ"**, và `_summary` (`:94`) không có ô đếm nào cho nó.
- UI `pillClass` (`Evaluation.tsx:17-23`) tô `"thiếu hồ sơ"` **cùng màu cam** với `"cần làm rõ"`.

Lưu ý tên: `_thieu_loai_ho_so` (`routers/evaluation.py:56`) đã tồn tại nhưng nghĩa **khác hẳn** —
nó trả tên các file HSDT *chưa gán loại hồ sơ*. Không tái dụng, không đặt tên gần giống.

### B1 — Loại hồ sơ nhà thầu chưa nộp

Tính ở **backend**, trong `results`. Không tính ở frontend: quy tắc loại trừ là logic nghiệp vụ,
và báo cáo Word/Excel về sau cũng cần cùng con số.

```
tập YÊU CẦU   = hợp mọi `hsdt_can_kiem_tra` của các tiêu chí trong gói
              − tài liệu DÙNG CHUNG  (artifact_catalog.la_dung_chung)
              − loại chỉ áp dụng hình thức KHÁC với nhà thầu này
tập ĐÃ NHẬN   = {h.loai_ho_so for h in ve.ho_so_nhan_duoc}
tập CHƯA NỘP  = YÊU CẦU − ĐÃ NHẬN
```

**Chuẩn hoá trước khi so:** `ho_so_nhan_duoc.loai_ho_so` đã được `inventory_pages`
(`experiment/evaluate/route.py:63`) ghi ở dạng `_norm` (thường, bỏ dấu, `đ→d`, giữ gạch dưới),
trong khi `hsdt_can_kiem_tra` là mã catalog do decompose sinh. So hai tập phải đi qua **cùng
`_norm`** — đây là cách route/pages_by_type trong lõi eval vẫn dùng, nên không sinh quy tắc khớp
thứ hai. Giữ lại mã gốc (chưa `_norm`) để hiển thị nhãn qua `artifact_catalog`.

Hai phép trừ đều có lý do nghiệp vụ cụ thể:

- **Tài liệu dùng chung.** `webform` (kết quả mở thầu) do bên mời thầu công bố cho cả gói, không
  phải thứ nhà thầu nộp. Báo "nhà thầu chưa nộp webform" là quy kết sai. Dùng
  `artifact_catalog.la_dung_chung(code)` — cùng hàm mà lõi eval dùng để lọc dữ liệu nhà thầu khác
  ra khỏi prompt, nên không phát sinh nguồn sự thật thứ hai.
- **Loại chỉ áp dụng hình thức khác.** Một loại bị loại khỏi tập yêu cầu khi **mọi** nội dung trỏ
  tới nó đều có `ap_dung` lệch với `hinh_thuc` đã dò của nhà thầu (`HsdtVendorEval.hinh_thuc`).
  Nhà thầu độc lập không bị báo thiếu `thoa_thuan_lien_danh`. Đọc `ap_dung` từ
  `RubricNoiDung.ap_dung` (`models.py:113`) — **không** cài lại phép gate của
  `evaluate._gate_khong_ap_dung`; chỉ đọc cùng dữ liệu đầu vào mà nó đọc.
  `hinh_thuc` rỗng (không rõ) → **không trừ gì** (fail-safe: thà báo thừa còn hơn giấu mất một
  loại hồ sơ thật sự thiếu).

Mỗi mục trong tập CHƯA NỘP kèm **tên các tiêu chí cần loại hồ sơ đó**, để chuyên gia thấy ngay hệ
quả thay vì phải tự tra ngược.

Payload `results` thêm cho mỗi nhà thầu:

```json
"ho_so_chua_nop": [
  {"loai_ho_so": "bao_dam_du_thau", "tieu_chi": ["Bảo đảm dự thầu", "..."]}
]
```

### B2 — Đếm riêng "thiếu hồ sơ", không gộp vào "cần làm rõ"

Vì roll-up không bao giờ cho tiêu chí kết quả `"thiếu hồ sơ"`, ô đếm phải định nghĩa lại cho đúng:

**Đếm số TIÊU CHÍ có ít nhất một verdict `"thiếu hồ sơ"`**, và trình bày như **khoản mục con của
"cần làm rõ"**, không phải ô đếm ngang hàng:

> cần làm rõ: 4 — trong đó thiếu hồ sơ: 2

Lý do chọn cách này thay vì thêm ô ngang hàng: mọi ô đếm hiện có đều đếm **tiêu chí** và cộng lại
đúng bằng `n_tieu_chi` (`n_dat + n_khong_dat + n_can_lam_ro + n_khong_ap_dung`). Thêm một ô ngang
hàng sẽ phá đẳng thức đó và làm bảng tổng hợp nói dối. Đếm verdict thay vì tiêu chí cũng phá vì
đơn vị khác hẳn.

`_summary` thêm khoá `n_thieu_ho_so`; `EvalSummary` (frontend types) thêm field tương ứng
(optional, để payload cũ không vỡ).

### B3 — UI

- `pillClass` tách `"thiếu hồ sơ"` khỏi nhánh mặc định `can-lam-ro`, cho class/màu riêng. Hiện nó
  dùng chung màu cam với "cần làm rõ" nên chuyên gia không phân biệt được "AI chưa đủ căn cứ" với
  "nhà thầu không nộp tài liệu" — hai việc cần hai hành động khác nhau.
- Tab "Tổng hợp" (bảng so sánh nhà thầu): cột "Cần làm rõ" hiện thêm phần trong đó thiếu hồ sơ.
- Đầu mỗi tab nhà thầu: khi `ho_so_chua_nop` khác rỗng, hiện thẻ liệt kê loại hồ sơ chưa nộp kèm
  tiêu chí bị ảnh hưởng. Rỗng thì không hiện gì (không thêm nhiễu cho ca đủ hồ sơ).

### Files chạm

`backend/routers/evaluation.py`, `backend/tests/test_evaluation_api.py`,
`frontend/src/api/types.ts`, `frontend/src/pages/Evaluation.tsx`, và file CSS chứa
`verdict-result-pill`.

---

## Kiểm thử

**Phần A**
- Upload PDF **scan** kèm `artifact_type` → 200, `artifact_validation` là `None`, và **không có
  call LLM nào** (spy trên `validate_artifact` / `ai_call`).
- Upload PDF **có text nhúng** kèm `artifact_type` → vẫn gọi kiểm loại như cũ, hành vi không đổi.
- `PATCH` đổi loại hồ sơ trên tài liệu scan (`extracted_text = "[]"`) → không gọi LLM,
  `artifact_validation` về `None`.
- `PATCH` trên tài liệu có text → vẫn kiểm như cũ.
- Hồi quy: test hiện có `test_upload_hsdt_thieu_loai_ho_so_bi_tu_choi` phải xanh nguyên trạng.

**Phần B**
- `ho_so_chua_nop` loại đúng `webform` khỏi danh sách dù nhiều tiêu chí khai nó.
- Nhà thầu `hinh_thuc="độc lập"`: `thoa_thuan_lien_danh` **không** nằm trong danh sách khi mọi nội
  dung trỏ tới nó đều `ap_dung="lien_danh"`.
- Nhà thầu `hinh_thuc="liên danh"` không nộp thỏa thuận liên danh → loại đó **có** trong danh sách.
- `hinh_thuc=""` (không rõ) → không trừ theo hình thức (fail-safe), loại vẫn bị báo thiếu.
- Mỗi mục kèm đúng tên các tiêu chí tham chiếu loại hồ sơ đó.
- Nhà thầu nộp đủ → `ho_so_chua_nop` là mảng rỗng.
- `n_thieu_ho_so` đếm đúng số **tiêu chí** có ≥1 verdict `"thiếu hồ sơ"`; một tiêu chí có 2 verdict
  thiếu vẫn đếm là 1.
- Đẳng thức tổng vẫn đúng: `n_tieu_chi == n_dat + n_khong_dat + n_can_lam_ro + n_khong_ap_dung`,
  và `n_thieu_ho_so <= n_can_lam_ro`.
- Payload cũ (không có `n_thieu_ho_so` / `ho_so_chua_nop`) không làm vỡ frontend.

## Thứ tự triển khai đề xuất

Phần A trước (rẻ, độc lập, và làm mọi lần thử tay sau đó nhanh hơn), rồi Phần B.
Trong Phần B: B2 trước B1 — B2 chỉ đụng `_summary` + UI, B1 cần thêm phép tính và dữ liệu mới.
