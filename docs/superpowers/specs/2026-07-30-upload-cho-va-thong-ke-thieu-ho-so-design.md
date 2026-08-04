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
- **Loại chỉ áp dụng hình thức khác.** Một loại bị loại khỏi tập yêu cầu khi **mọi** nội dung xét
  đến đều lệch hình thức của nhà thầu (`HsdtVendorEval.hinh_thuc`). Nhà thầu độc lập không bị báo
  thiếu `thoa_thuan_lien_danh`. `hinh_thuc` rỗng (không rõ) → **không trừ gì** (fail-safe: thà báo
  thừa còn hơn giấu mất một loại hồ sơ thật sự thiếu).

  > **Sửa sau review (2026-07-30, chủ dự án quyết):** bản đầu chỉ đọc trường `ap_dung`. Thiếu.
  > `evaluate._gate_khong_ap_dung` còn coi mọi nội dung có `hsdt_kiem_tra ∈ _HO_SO_CHI_LIEN_DANH`
  > là chỉ-liên-danh **bất kể `ap_dung`** — fallback đó tồn tại vì `ap_dung` do LLM gán lúc
  > decompose nên có thể khuyết. Chỉ đọc `ap_dung` thì khi decompose quên gán cờ, cùng một trang sẽ
  > hiện verdict "không áp dụng" mà banner vẫn báo "chưa nộp thỏa thuận liên danh". Quyết định: xét
  > **cả hai tín hiệu**, **import `_HO_SO_CHI_LIEN_DANH`** dùng chung thay vì chép cứng chuỗi.
  >
  > Review cuối nhánh bổ sung một lỗ cùng loại: loại hồ sơ chỉ đóng vai trò **tài liệu đối chiếu**
  > không có nội dung nào trỏ tới nó, nên luôn rơi vào fail-safe và luôn bị báo — kể cả khi cả tiêu
  > chí đã "không áp dụng". Sửa: không có nội dung nào trỏ tới loại đó thì lùi lên xét **cả tiêu
  > chí**; mọi nội dung của tiêu chí đều lệch hình thức → không kéo tài liệu đối chiếu vào. Tiêu chí
  > trộn nội dung chung với nội dung liên danh thì VẪN giữ loại.

Mỗi mục trong tập CHƯA NỘP kèm **tên các tiêu chí cần loại hồ sơ đó**, để chuyên gia thấy ngay hệ
quả thay vì phải tự tra ngược.

**Mã loại hồ sơ phải ép về catalog** (`artifact_catalog.resolve_code`, giữ mã gốc khi không tra
được): `hsdt_can_kiem_tra` do LLM sinh và không được snap ở đâu cả, nên alias của `webform`
(`ket_qua_mo_thau`, `bien_ban_mo_thau`) sẽ trượt `la_dung_chung` và quy kết nhà thầu chưa nộp tài
liệu của **bên mời thầu** — đúng thứ phép trừ này sinh ra để chặn.

**Nhà thầu chưa được chấm lần nào** (`HsdtVendorEval` chưa tồn tại) → trả **danh sách rỗng**. Không
có `ho_so_nhan_duoc` nghĩa là chưa có căn cứ, không phải nhà thầu nộp thiếu; báo "chưa nộp" lúc đó
là khẳng định sai sự thật, và mâu thuẫn với chính thẻ "Chưa có kết quả đánh giá" ngay cạnh. Khác
hẳn ca đã chấm mà `ho_so_nhan_duoc` rỗng — ca đó vẫn phải báo.

Payload `results` thêm cho mỗi nhà thầu:

```json
"ho_so_chua_nop": [
  {"loai_ho_so": "bao_dam_du_thau", "tieu_chi": ["Bảo đảm dự thầu", "..."]}
]
```

### B2 — Đếm riêng "thiếu hồ sơ", không gộp vào "cần làm rõ"

> **ĐÃ BỊ THAY THẾ (2026-07-30, sau khi dùng thử).** Toàn bộ mục B2 này — `n_thieu_ho_so` là "lát
> cắt độc lập" nằm ngoài đẳng thức bốn ô — đã bị đảo. Chủ dự án thấy bảng tổng hợp cộng ra 11 trên
> 10 tiêu chí là không đọc được, và yêu cầu "thiếu hồ sơ" trở thành kết luận cấp tiêu chí thật với
> tổng bằng số tiêu chí. Xem `2026-07-30-rollup-thieu-ho-so-thanh-o-dem-design.md`. Đừng làm theo
> mục B2 dưới đây.

Vì roll-up không bao giờ cho tiêu chí kết quả `"thiếu hồ sơ"`, ô đếm phải định nghĩa lại cho đúng:

**Đếm số TIÊU CHÍ có ít nhất một verdict `"thiếu hồ sơ"`**, đơn vị TIÊU CHÍ để cùng đơn vị với các
ô còn lại (một tiêu chí có hai nội dung cùng thiếu vẫn đếm là một).

> **Sửa sau review (2026-07-30, chủ dự án quyết):** bản đầu của spec này định nghĩa `n_thieu_ho_so`
> là **khoản mục con của "cần làm rõ"** và trình bày lồng trong ô đó. Sai. `_rollup` ưu tiên
> `"không đạt"` TRƯỚC `{SOI, THIEU, LOI}`, nên một tiêu chí có cả verdict `"không đạt"` lẫn
> `"thiếu hồ sơ"` rơi vào `n_khong_dat` — mà vẫn được đếm — cho ra `n_thieu_ho_so > n_can_lam_ro`
> và UI hiện "0 cần làm rõ (1 thiếu hồ sơ)": một khoản mục con lớn hơn cha, đúng thứ spec này viết
> ra để tránh.
>
> Quyết định: **giữ phép đếm** (đếm mọi tiêu chí có verdict thiếu hồ sơ — lọc theo roll-up sẽ giấu
> mất việc thiếu tài liệu ở đúng những tiêu chí đã có vấn đề khác, là chỗ chuyên gia cần biết
> nhất), nhưng `n_thieu_ho_so` là **LÁT CẮT ĐỘC LẬP** nằm NGOÀI đẳng thức bốn ô, trình bày bằng
> Tag/cột RIÊNG. Đẳng thức `n_tieu_chi = n_dat + n_khong_dat + n_can_lam_ro + n_khong_ap_dung` vẫn
> đúng vì `n_thieu_ho_so` không tham gia phép cộng đó.

`_summary` thêm khoá `n_thieu_ho_so`; `EvalSummary` (frontend types) thêm field tương ứng
(optional, để payload cũ không vỡ).

### B3 — UI

- **Sửa sau review:** bản đầu yêu cầu tách màu ở `pillClass`. Sai chỗ — `ResultPill` chỉ dùng ở cấp
  **tiêu chí**, mà tiêu chí không bao giờ mang kết quả `"thiếu hồ sơ"` (cả hai roll-up đều cuộn nó
  thành `"cần làm rõ"`), nên nhánh đó là code chết. Chỗ chuyên gia thật sự thấy `"thiếu hồ sơ"` là
  ô `Select` cấp **verdict** — mà `KQ_OPTS` lại thiếu giá trị đó nên verdict ấy hiện thành chữ trần
  và dropdown âm thầm chỉ có bốn lựa chọn. Quyết định: xóa nhánh chết + CSS thừa, bổ sung
  `"thiếu hồ sơ"` vào `KQ_OPTS`. Ô verdict là `antd Select` thuần (mọi giá trị đều không màu) nên
  phân biệt bằng nhãn, không tô màu riêng.
- Tab "Tổng hợp" (bảng so sánh nhà thầu): thêm **cột riêng** "Thiếu hồ sơ" ngay sau cột "Cần làm
  rõ"; cột "Cần làm rõ" giữ nguyên, không lồng chú thích vào.
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
- Đẳng thức tổng vẫn đúng: `n_tieu_chi == n_dat + n_khong_dat + n_can_lam_ro + n_khong_ap_dung`.
  **KHÔNG** assert `n_thieu_ho_so <= n_can_lam_ro` — bất biến đó đã bị bác (xem mục B2): tiêu chí
  có cả "không đạt" lẫn "thiếu hồ sơ" làm `n_thieu_ho_so` vượt `n_can_lam_ro` một cách hợp lệ.
- Nhà thầu chưa chấm lần nào → `ho_so_chua_nop == []`; đã chấm mà `ho_so_nhan_duoc` rỗng → vẫn liệt kê.
- Tiêu chí toàn nội dung `ap_dung="lien_danh"` + nhà thầu độc lập → tài liệu đối chiếu của tiêu chí
  đó (vd `giay_uy_quyen`) **không** bị liệt; thêm một nội dung `ap_dung=""` vào tiêu chí đó → **có**.
- Tiêu chí khai alias (`ket_qua_mo_thau`) → vẫn nhận ra là `webform`, không bị liệt. Khai
  `bao_lanh_du_thau` trong khi nhà thầu đã nộp `bao_dam_du_thau` → không bị liệt.
- Payload cũ (không có `n_thieu_ho_so` / `ho_so_chua_nop`) không làm vỡ frontend.

## Thứ tự triển khai đề xuất

Phần A trước (rẻ, độc lập, và làm mọi lần thử tay sau đó nhanh hơn), rồi Phần B.
Trong Phần B: B2 trước B1 — B2 chỉ đụng `_summary` + UI, B1 cần thêm phép tính và dữ liệu mới.

## Nợ kỹ thuật còn lại (đã triển khai xong, cố ý hoãn)

Review cuối nhánh (2026-07-30) nêu và chủ dự án đồng ý hoãn:

1. **`artifact_validation` giữ `{}` khi `validate_artifact` NÉM lỗi** (vd LLM timeout) với file có
   text — vi phạm cùng hợp đồng "không có kết luận thì `None`" mà Phần A vừa dựng. Lỗi có từ trước;
   `{}` là falsy với consumer duy nhất (`?.match === false`) nên không sinh cảnh báo giả. Gộp vào
   lần tới khi đụng phần xử lý lỗi của `upload_document`.
2. **Không có test tự động cho state `uploading`** ở frontend — repo chưa có hạ tầng test component
   cho file đó; dựng Vitest + Testing Library cho một boolean là không tương xứng.
3. **`EvalResult.summary` (`experiment/evaluate/schema.py`) là bản đếm thứ hai**, không có
   `n_thieu_ho_so`. Frontend không đi đường đó nên chưa lộ; đã thêm comment trỏ đường ở cả hai phía.
4. **Báo cáo Word/Excel chưa mang số liệu mới** — `services/reports.py` dùng shape cũ. Spec B1 viện
   dẫn "báo cáo về sau cũng cần cùng con số" làm một lý do tính ở backend, nên đây là việc tiếp theo
   đã biết trước.
5. **Skew giữa rubric hiện tại và ảnh chụp lúc chấm:** `_ho_so_chua_nop` đọc `RubricCriterion` HIỆN
   TẠI còn `ho_so_nhan_duoc` là ảnh chụp lúc chấm. Sửa rubric sau khi chấm làm banner mô tả một
   rubric mà các verdict bên dưới chưa từng thấy.
6. **Một cờ `uploading` làm cả bốn nút upload cùng quay** — chặn upload đồng thời là đúng, nhưng
   spinner nên nằm ở đúng nút được bấm.
7. **`--teal` đọc như màu tích cực** (nó là màu nút chính của app), trong khi cột "Thiếu hồ sơ" dùng
   nó cho một con số cần chú ý. Bảng token hẹp nên đây là lựa chọn có cân nhắc, không phải sơ suất.
